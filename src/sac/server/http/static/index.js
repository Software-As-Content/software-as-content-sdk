import { SaCRenderer } from '/renderer/sac-renderer.js';

// ─── Renderer setup ───────────────────────────────────────────

const iframe = document.getElementById('preview');
const placeholder = document.getElementById('placeholder');
const previewNotice = document.getElementById('preview-notice');
let renderer = createRenderer();

function createRenderer() {
  const r = new SaCRenderer(iframe);
  r.on('render', () => {
    placeholder.classList.add('hidden');
    iframe.classList.remove('hidden');
    hidePreviewNotice();
  });
  r.on('error', (err) => {
    showPreviewNotice('Generated app needs a revision', `${err.type || 'render'}: ${err.message || err}`);
    showStatus('Render issue detected. The conversation is still active.', 'error');
  });
  r.on('action', ({ intent, context }) => {
    if (!conversationId || !intent) return;
    addChatMsg('user', intent);
    routeUserIntent(intent, context);
  });
  return r;
}

function resetRenderer() {
  // Destroy old renderer and recreate
  if (renderer && renderer.destroy) renderer.destroy();
  renderer = createRenderer();
}

// ─── State ────────────────────────────────────────────────────

let conversationId = null;
let currentVersion = 0;
let callbackUrl = null;       // null = standalone mode; set = external-agent mode
let eventSource = null;        // SSE subscription to /c/{id}/events
let pendingAction = false;     // true while waiting for agent/stream response
let appVersions = [];          // successful generation/growth events with code snapshots
let viewedVersion = 0;         // version currently shown in the iframe
let statusTimer = null;
const callbackCards = new Map(); // run_id -> { el, eventsEl, rawEl, seen }

// ─── Tab switching ───────────────────────────────────────────

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.remove('hidden');
    if (tab.dataset.tab === 'conversations') loadConversations();
  });
});

// ─── Health check on load ────────────────────────────────────

(async () => {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    document.getElementById('health-dot').innerHTML =
      `<span class="dot dot-green"></span>${data.status}`;
    document.getElementById('version-badge').textContent = 'v' + data.version;
  } catch {
    document.getElementById('health-dot').innerHTML =
      `<span class="dot dot-red"></span>offline`;
  }
})();

// ─── Send handler (unified entry point) ──────────────────────

const sendBtn = document.getElementById('send-btn');
const intentInput = document.getElementById('intent');
const latestVersionBtn = document.getElementById('latest-version-btn');
const codeDisplay = document.getElementById('code-display');
const codeMeta = document.getElementById('code-meta');
const copyCodeBtn = document.getElementById('copy-code-btn');

sendBtn.addEventListener('click', () => handleSend());
intentInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
});
latestVersionBtn.addEventListener('click', () => {
  const latest = getLatestVersion();
  if (latest) applyAppVersion(latest);
});
copyCodeBtn.addEventListener('click', async () => {
  const code = codeDisplay.textContent || '';
  if (!code.trim()) return;
  try {
    await navigator.clipboard.writeText(code);
    flashStatus('Code copied', 'success', 1200);
  } catch {
    flashStatus('Copy failed', 'error', 1800);
  }
});

document.getElementById('new-conv-btn').addEventListener('click', () => {
  conversationId = null;
  currentVersion = 0;
  viewedVersion = 0;
  appVersions = [];
  callbackUrl = null;
  if (eventSource) { eventSource.close(); eventSource = null; }
  document.getElementById('conv-info').textContent = '';
  latestVersionBtn.classList.add('hidden');
    hidePreviewNotice();
  document.getElementById('chat-area').innerHTML =
    '<div class="chat-msg system"><div class="chat-bubble">New conversation started.</div></div>';
  callbackCards.clear();
  placeholder.classList.remove('hidden');
  iframe.classList.add('hidden');
  resetRenderer();
  hideSuggestions();
  hideStatus();
  codeDisplay.textContent = '';
  codeMeta.textContent = 'No app version selected';
});

async function handleSend() {
  const message = intentInput.value.trim();
  if (!message || pendingAction) return;

  setPending(true);
  intentInput.value = '';
  addChatMsg('user', message);

  // External-agent mode: forward to /c/{id}/action; agent posts result back
  // to /inbox; SSE delivers it. No local streamGenerate path.
  // pendingAction stays true — cleared when SSE delivers version/chat event.
  if (callbackUrl && conversationId) {
    showStatus('Sent to agent, waiting...', 'running');
    try {
      const res = await fetch(`/c/${conversationId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent: message }),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => '');
        addChatMsg('system', `Forwarding failed (HTTP ${res.status}): ${detail}`);
        hideStatus();
        setPending(false);
      }
      // On success: don't clear pending — wait for SSE event
    } catch (err) {
      addChatMsg('system', 'Error: ' + err.message);
      hideStatus();
      setPending(false);
    }
    return;
  }

  // Standalone mode (no callback registered): legacy classify + local stream
  showStatus('Thinking...', 'running');
  try {
    const res = await fetch('/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
    const data = await res.json();

    if (data.conversation_id && data.conversation_id !== conversationId) {
      conversationId = data.conversation_id;
      setupEventSource(conversationId);
    }

    if (data.type === 'chat') {
      addChatMsg('assistant', data.reply || '...');
      hideStatus();
      setPending(false);
    } else {
      addChatMsg('system', data.type === 'generate' ? 'Generating UI...' : 'Evolving UI...');
      await streamGenerate({ intent: message, conversation_id: conversationId });
      // streamGenerate clears pending on complete/error
    }
  } catch (err) {
    addChatMsg('system', 'Error: ' + err.message);
    hideStatus();
    setPending(false);
  }
}

// Routes any user-originated intent (button click in App, suggestion click,
// etc.) to either the external agent (via /c/{id}/action) or the local
// stream pipeline.
async function routeUserIntent(intent, context = null) {
  if (pendingAction) return;  // debounce — wait for current action to finish
  setPending(true);

  if (callbackUrl) {
    showStatus('Sent to agent, waiting...', 'running');
    try {
      const res = await fetch(`/c/${conversationId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent, context }),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => '');
        addChatMsg('system', `Forwarding failed (HTTP ${res.status}): ${detail}`);
        hideStatus();
        setPending(false);
      }
      // On success: callback_run/version SSE events clear pending.
    } catch (err) {
      addChatMsg('system', 'Error: ' + err.message);
      hideStatus();
      setPending(false);
    }
  } else {
    await streamGenerate({ intent, conversation_id: conversationId });
    // streamGenerate clears pending on complete/error
  }
}

// ─── SSE: subscribe to /c/{id}/events ────────────────────────

function setupEventSource(convId) {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (!convId) return;

  const es = new EventSource(`/c/${convId}/events`);
  eventSource = es;

  es.addEventListener('version', async (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    // New App version pushed by an agent — fetch latest code and re-render.
    try {
      const res = await fetch('/conversations/' + convId);
      const { conversation, events = [] } = await res.json();
      if (conversation && conversation.latest_code) {
        appVersions = extractAppVersions(events);
        const latest = appVersions[appVersions.length - 1];
        currentVersion = latest?.version || data.version || currentVersion;
        if (latest) {
          ensureVersionCard(latest);
          applyAppVersion(latest, { announce: true });
        } else {
          setConversationInfo(`Updated to v${currentVersion}`, `${conversation.latest_code.length} chars`);
          codeDisplay.textContent = conversation.latest_code;
          codeMeta.textContent = `Updated to v${currentVersion} · ${formatCodeSize(conversation.latest_code)}`;
          placeholder.classList.add('hidden');
          iframe.classList.remove('hidden');
          renderer.render(conversation.latest_code);
          addChatMsg('system', `Updated to v${currentVersion}`);
          flashStatus(`App updated to v${currentVersion}`, 'success');
        }
        setPending(false);

        // Refresh suggestions from the latest event
        const last = [...events].reverse().find(
          (ev) => (ev.type === 'generation' || ev.type === 'growth') && ev.status === 'success'
        );
        renderSuggestions(last?.intent_suggestions || []);
        markLatestCallbackVersion(data.version);
      }
    } catch (err) {
      console.warn('Failed to apply version event', err);
    }
  });

  es.addEventListener('chat', (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    addChatMsg(data.role || 'assistant', data.content || '');
    hideStatus();
    setPending(false);
  });

  es.addEventListener('callback_run', (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    renderCallbackRun(data);
    if (data.status === 'queued') {
      showStatus(`Callback queued (${adapterLabel(data.adapter)})`, 'running');
    } else if (data.status === 'running') {
      showStatus(`Callback running (${adapterLabel(data.adapter)})`, 'running');
    } else if (data.status === 'failed') {
      showStatus(`Callback failed (${adapterLabel(data.adapter)})`, 'error');
      setPending(false);
    } else if (data.status === 'succeeded') {
      flashStatus(`Callback completed (${adapterLabel(data.adapter)})`, 'success');
      setPending(false);
    }
  });

  es.addEventListener('callback_log', (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    renderCallbackLog(data);
  });

  es.addEventListener('ping', () => {
    // keepalive — ignore
  });

  es.onerror = (err) => {
    // EventSource auto-reconnects; just log.
    console.warn('SSE connection issue, will retry', err);
  };
}

function renderSuggestions(suggestions) {
  const area = document.getElementById('suggestions-area');
  const list = document.getElementById('suggestions-list');
  if (!suggestions || suggestions.length === 0) {
    area.classList.add('hidden');
    return;
  }
  area.classList.remove('hidden');
  const label = document.querySelector('.suggestions-label');
  if (label) label.textContent = 'Next actions';
  list.innerHTML = suggestions.map(s =>
    `<button class="suggestion-btn" data-prompt="${escHtml(s.prompt)}" title="${escHtml(s.label)}">${escHtml(s.label)}</button>`
  ).join('');
  list.querySelectorAll('.suggestion-btn').forEach(b => {
    b.addEventListener('click', () => {
      const intent = b.dataset.prompt;
      addChatMsg('user', intent);
      routeUserIntent(intent);
    });
  });
}

// ─── Streaming generation (POST-based SSE) ───────────────────

async function streamGenerate(body) {
  showStatus('Generating...', 'running');

  codeDisplay.textContent = '';
  codeDisplay.style.color = '';
  codeMeta.textContent = 'Streaming generated code...';

  placeholder.classList.add('hidden');
  iframe.classList.remove('hidden');

  const stream = renderer.createStream();
  let codeBuffer = '';
  let inCodeFence = false;

  try {
    const response = await fetch('/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ') && currentEvent) {
          try {
            const data = JSON.parse(line.slice(6));
            handleSSEEvent(currentEvent, data, stream, codeDisplay);
          } catch {}
          currentEvent = null;
        }
      }
    }
  } catch (err) {
    showStatus('Connection error: ' + err.message, 'error');
    stream.abort();
    setPending(false);
  }
}

// Track code fence stripping state per stream
let fenceState = { started: false, firstLine: true };

function handleSSEEvent(eventType, data, stream, codeDisplay) {
  switch (eventType) {
    case 'stage':
      showStatus(`${data.name}: ${data.status}`, 'running');
      break;

    case 'search': {
      const results = data.results || [];
      if (results.length > 0) {
        const area = document.getElementById('suggestions-area');
        const list = document.getElementById('suggestions-list');
        const label = document.querySelector('.suggestions-label');
        area.classList.remove('hidden');
        if (label) label.textContent = 'Sources';
        list.innerHTML = results.map(r =>
          `<span style="font-size:12px;color:#78716c;">${escHtml(r.query)} (${r.sources?.length || 0})</span>`
        ).join('');
      }
      break;
    }

    case 'chunk': {
      let chunk = data.data;
      // Display raw in code panel
      codeDisplay.textContent += chunk;
      // Stream to renderer (it handles fence stripping internally)
      stream.push(chunk);
      break;
    }

    case 'complete': {
      stream.end();
      const app = data.app;
      if (data.conversation_id) conversationId = data.conversation_id;
      currentVersion = app.version;
      const version = {
        version: app.version,
        title: app.intent || `Version ${app.version}`,
        code: app.code,
        kind: app.parent_version ? 'evolved' : 'generated',
        createdAt: app.created_at,
      };
      upsertAppVersion(version);

      // Update header
      applyAppVersion(version);

      // Show completion in chat
      ensureVersionCard(version);

      // Show suggestions
      renderSuggestions(app.suggestions || []);

      const stages = (app.stages || []).map(s =>
        `${s.name}: ${s.duration ? s.duration.toFixed(1) + 's' : s.status}`
      ).join(' → ');
      flashStatus(stages || `App updated to v${version.version}`, 'success');
      setPending(false);
      break;
    }

    case 'error':
      showStatus('Error: ' + data.error, 'error');
      addChatMsg('system', 'Error: ' + data.error);
      stream.abort();
      setPending(false);
      break;
  }
}

// ─── Chat UI helpers ─────────────────────────────────────────

function addChatMsg(role, content) {
  const area = document.getElementById('chat-area');
  const msg = document.createElement('div');
  msg.className = `chat-msg ${role}`;
  msg.innerHTML = `<div class="chat-bubble">${escHtml(content)}</div>`;
  area.appendChild(msg);
  scrollChatToBottom();
}

function extractAppVersions(events) {
  const versions = [];
  for (const event of events || []) {
    if ((event.type === 'generation' || event.type === 'growth') && event.status === 'success' && event.code) {
      versions.push({
        version: versions.length + 1,
        title: event.intent || `Version ${versions.length + 1}`,
        code: event.code,
        kind: event.type === 'generation' ? 'generated' : 'evolved',
        createdAt: event.timestamp,
        suggestions: event.intent_suggestions || [],
      });
    }
  }
  return versions;
}

function upsertAppVersion(version) {
  const index = appVersions.findIndex(v => v.version === version.version);
  if (index >= 0) {
    appVersions[index] = version;
  } else {
    appVersions.push(version);
  }
}

function getLatestVersion() {
  return appVersions[appVersions.length - 1] || null;
}

function applyAppVersion(version, opts = {}) {
  if (!version || !version.code) return;
  viewedVersion = version.version;
  codeDisplay.textContent = version.code;
  codeMeta.textContent = `v${version.version} · ${formatCodeSize(version.code)}`;
  placeholder.classList.add('hidden');
  iframe.classList.remove('hidden');
  hidePreviewNotice();
  renderer.render(version.code);
  setConversationInfo(`Viewing v${version.version}`, compactText(version.title, 34));
  markActiveVersionCard(version.version);
  updateLatestButton();
    if (opts.announce) {
    addChatMsg('system', `App updated to v${version.version}`);
    flashStatus(`App updated to v${version.version}`, 'success');
    flashVersionCard(version.version);
  }
}

function ensureVersionCard(version) {
  const area = document.getElementById('chat-area');
  const id = `version-card-${version.version}`;
  let button = document.getElementById(id);
  if (!button) {
    button = document.createElement('button');
    button.id = id;
    button.type = 'button';
    button.className = 'version-card';
    button.addEventListener('click', () => applyAppVersion(version));
    area.appendChild(button);
  }
  button.innerHTML = `
    <span class="version-card-top">
      <span class="version-card-badge">v${version.version}</span>
      <span class="version-card-kind">${escHtml(version.kind || 'version')}</span>
    </span>
    <span class="version-card-title">${escHtml(version.title || `Version ${version.version}`)}</span>
    <span class="version-card-meta">${version.createdAt ? escHtml(formatTime(version.createdAt)) : `${version.code.length} chars`}</span>
    <span class="version-card-footer">
      <span>${escHtml(formatCodeSize(version.code))}</span>
      <span class="version-card-cta">View version →</span>
    </span>
  `;
  markActiveVersionCard(viewedVersion);
  updateLatestButton();
    scrollChatToBottom();
}

function markActiveVersionCard(versionNumber) {
  document.querySelectorAll('.version-card').forEach(card => {
    card.classList.toggle('active', card.id === `version-card-${versionNumber}`);
  });
}

function flashVersionCard(versionNumber) {
  const card = document.getElementById(`version-card-${versionNumber}`);
  if (!card) return;
  card.classList.remove('just-updated');
  void card.offsetWidth;
  card.classList.add('just-updated');
  window.setTimeout(() => card.classList.remove('just-updated'), 1500);
}

function updateLatestButton() {
  const latest = getLatestVersion();
  latestVersionBtn.classList.toggle('hidden', !latest || viewedVersion >= latest.version);
}


function renderCallbackRun(run) {
  const shortId = (run.id || '').slice(0, 8);
  const card = ensureCallbackCard(run);
  const status = run.status || 'unknown';
  const title = card.el.querySelector('.callback-card-title');
  const subtitle = card.el.querySelector('.callback-card-subtitle');
  const meta = card.el.querySelector('.callback-card-meta');
  const statusEl = card.el.querySelector('.callback-status');

  card.el.className = `callback-card ${escClass(status)}`;
  title.textContent = `${adapterLabel(run.adapter)} agent bridge`;
  subtitle.textContent = compactText(run.intent || run.last_event || 'Waiting for agent activity', 140);
  const facts = [`#${shortId}`];
  if (run.cwd && status === 'running') facts.push(compactPath(run.cwd));
  if (run.returncode !== undefined) facts.push(`exit ${run.returncode}`);
  if (run.error) facts.push(compactText(run.error, 80));
  meta.textContent = facts.join(' · ');
  statusEl.textContent = runStatusLabel(status);
  statusEl.className = `callback-status ${status}`;

  if (run.status === 'failed' && run.stderr_tail) {
    appendCallbackRaw(run.id, 'stderr tail', run.stderr_tail.slice(-1200));
  }
  if (Array.isArray(run.logs)) {
    for (const log of run.logs.slice(-8)) renderCallbackLog(log);
  }
}

function renderCallbackLog(log) {
  if (!log.run_id) return;
  const card = ensureCallbackCard({ id: log.run_id, adapter: 'codex_exec_resume', status: 'running' });
  let label = log.label || `${log.stream || 'callback'} log`;
  let detail = log.detail || '';
  const commandSummary = summarizeCommandLog(label, detail || log.line);
  if (commandSummary) {
    label = commandSummary.label;
    detail = commandSummary.detail;
    if (log.line || log.detail) appendCallbackRaw(log.run_id, log.label || label, log.line || log.detail);
  }
  const isDiagnosticNoise =
    label === 'stderr log' ||
    log.kind === 'warning' ||
    /ignoring interface\.|stream disconnected|manifest|loader/.test(detail);
  if (isDiagnosticNoise) {
    if (log.line || detail) appendCallbackRaw(log.run_id, label, log.line || detail);
    return;
  }
  const eventKey = `${log.timestamp || ''}:${log.kind || ''}:${log.label || ''}:${log.detail || ''}`;
  if (card.seen.has(eventKey)) return;
  card.seen.add(eventKey);

  const event = document.createElement('div');
  event.className = `callback-event ${escClass(log.kind || 'log')}`;
  event.innerHTML = `
    <span class="callback-event-dot"></span>
    <span>
      <span class="callback-event-label">${escHtml(label)}</span>
      ${detail ? `<div class="callback-event-detail">${escHtml(compactText(detail, 500))}</div>` : ''}
    </span>`;
  card.eventsEl.appendChild(event);

  while (card.eventsEl.children.length > 5) card.eventsEl.removeChild(card.eventsEl.firstChild);
  if (log.raw_visible && log.line) appendCallbackRaw(log.run_id, label, log.line);
  scrollChatToBottom();
}

function summarizeCommandLog(label, text) {
  if (!/^Command (started|completed)$/i.test(label || '')) return null;
  const raw = String(text || '');
  const inboxTarget = raw.includes('/inbox') ? 'POST /inbox' : 'Command';
  const state = /completed/i.test(label) ? 'completed' : 'started';
  return {
    label: `Agent bridge ${state}`,
    detail: inboxTarget,
  };
}

function ensureCallbackCard(run) {
  let card = callbackCards.get(run.id);
  if (card) return card;

  const area = document.getElementById('chat-area');
  const el = document.createElement('div');
  el.className = 'callback-card';
  el.dataset.runId = run.id;
  el.innerHTML = `
    <div class="callback-card-header">
      <div class="callback-card-main">
        <div class="callback-icon">↔</div>
        <div>
          <div class="callback-card-title">${escHtml(adapterLabel(run.adapter))} agent bridge</div>
          <div class="callback-card-subtitle">Waiting for agent activity</div>
          <div class="callback-card-meta">#${escHtml((run.id || '').slice(0, 8))}</div>
        </div>
      </div>
      <span class="callback-status ${escClass(run.status || 'queued')}">${escHtml(runStatusLabel(run.status || 'queued'))}</span>
    </div>
    <div class="callback-events"></div>`;
  area.appendChild(el);
  card = { el, eventsEl: el.querySelector('.callback-events'), rawEl: null, rawCount: 0, seen: new Set() };
  callbackCards.set(run.id, card);
  scrollChatToBottom();
  return card;
}

function appendCallbackRaw(runId, label, raw) {
  const card = callbackCards.get(runId);
  if (!card || !raw) return;
  if (!card.rawEl) {
    card.rawEl = document.createElement('details');
    card.rawEl.className = 'callback-raw';
    card.rawEl.innerHTML = '<summary>Diagnostics</summary><pre></pre>';
    card.el.appendChild(card.rawEl);
  }
  card.rawCount += 1;
  card.rawEl.querySelector('summary').textContent = `Diagnostics (${card.rawCount})`;
  const pre = card.rawEl.querySelector('pre');
  pre.textContent = `${pre.textContent}${pre.textContent ? '\n\n' : ''}[${label}]\n${String(raw).slice(0, 2000)}`.slice(-8000);
}

function markLatestCallbackVersion(version) {
  const cards = Array.from(callbackCards.values());
  const card = cards.reverse().find(c => {
    const statusEl = c.el.querySelector('.callback-status');
    return statusEl?.classList.contains('running') ||
      statusEl?.classList.contains('queued') ||
      statusEl?.classList.contains('succeeded');
  });
  if (!card) return;
  const event = {
    run_id: card.el.dataset.runId,
    kind: 'version_updated',
    label: `App updated to v${version}`,
  };
  renderCallbackLog(event);
}

// ─── API Explorer helpers ────────────────────────────────────

window.apiCall = async function(method, path, resultId) {
  const el = document.getElementById(resultId);
  el.textContent = 'Loading...';
  try {
    const res = await fetch(path, { method });
    const data = await res.json();
    el.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    el.textContent = 'Error: ' + err.message;
  }
};

window.apiSend = async function() {
  const el = document.getElementById('send-result');
  const message = document.getElementById('api-send-msg').value.trim();
  if (!message) return;
  el.textContent = 'Sending...';
  try {
    const res = await fetch('/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    const summary = { ...data };
    if (summary.app) {
      summary.app = {
        version: data.app.version,
        intent: data.app.intent,
        code_length: data.app.code?.length,
        model: data.app.model,
      };
    }
    el.textContent = JSON.stringify(summary, null, 2);
  } catch (err) {
    el.textContent = 'Error: ' + err.message;
  }
};

// ─── Conversations tab ───────────────────────────────────────

window.loadConversations = async function() {
  const container = document.getElementById('conv-list');
  try {
    const res = await fetch('/conversations');
    const data = await res.json();
    const convs = data.conversations || [];

    if (convs.length === 0) {
      container.innerHTML = '<p style="font-size:13px;color:#a8a29e;">No conversations yet.</p>';
      return;
    }

    container.innerHTML = convs.map(c => `
      <div class="conv-card ${c.id === conversationId ? 'active' : ''}" onclick="loadConv('${c.id}')">
        <div class="conv-card-header">
          <span class="conv-card-title">${escHtml(c.title || 'Untitled')}</span>
          <span class="conv-card-meta">${c.event_count} events</span>
        </div>
        <div class="conv-card-meta">
          ${c.id.substring(0, 8)}... | ${new Date(c.updated_at).toLocaleString()}
        </div>
        <div class="conv-card-actions" onclick="event.stopPropagation()">
          <input class="input-sm" id="rename-${c.id}" placeholder="Rename" style="flex:1;" onclick="event.stopPropagation()">
          <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); renameConv('${c.id}')">Rename</button>
          <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteConv('${c.id}')">Delete</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<p style="font-size:13px;color:#dc2626;">Error: ${err.message}</p>`;
  }
};

window.loadConv = async function(id) {
  try {
    const res = await fetch('/conversations/' + id);
    const data = await res.json();
    const conv = data.conversation;
    const events = data.events || [];

    conversationId = id;
    currentVersion = conv.event_count;
    callbackUrl = conv.callback_url || null;  // determines routing mode
    setupEventSource(id);                      // subscribe to live updates
    setConversationInfo(conv.title || 'Untitled', callbackUrl ? 'agent-driven' : 'local');
    appVersions = extractAppVersions(events);
    viewedVersion = appVersions[appVersions.length - 1]?.version || 0;

    // Rebuild chat from events
    const chatArea = document.getElementById('chat-area');
    chatArea.innerHTML = '';
    callbackCards.clear();

    let lastSuggestions = [];
    for (const evt of events) {
      if (evt.type === 'message') {
        addChatMsg(evt.role, evt.content);
      } else if (evt.type === 'generation' && evt.status === 'success') {
        const version = appVersions.find(v => v.code === evt.code);
        if (version) ensureVersionCard(version);
        if (evt.intent_suggestions?.length) lastSuggestions = evt.intent_suggestions;
      } else if (evt.type === 'growth' && evt.status === 'success') {
        const version = appVersions.find(v => v.code === evt.code);
        if (version) ensureVersionCard(version);
        if (evt.intent_suggestions?.length) lastSuggestions = evt.intent_suggestions;
      }
    }

    // Show suggestions from the last generation/growth event
    renderSuggestions(lastSuggestions);

    try {
      const runsRes = await fetch(`/c/${id}/callback-runs`);
      if (runsRes.ok) {
        const runsData = await runsRes.json();
        for (const run of (runsData.runs || []).slice(-5)) {
          renderCallbackRun(run);
        }
      }
    } catch {}

    // Render latest code if available
    const latestVersion = appVersions[appVersions.length - 1];
    if (latestVersion) {
      applyAppVersion(latestVersion);
    } else if (conv.latest_code) {
      const fallbackVersion = {
        version: currentVersion || 1,
        title: conv.latest_intent || conv.title || 'Latest version',
        code: conv.latest_code,
        kind: 'latest',
      };
      applyAppVersion(fallbackVersion);
    }

    // Switch to chat tab
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
    document.querySelector('[data-tab="chat"]').classList.add('active');
    document.getElementById('tab-chat').classList.remove('hidden');

    chatArea.scrollTop = chatArea.scrollHeight;
  } catch (err) {
    alert('Error loading conversation: ' + err.message);
  }
};

window.renameConv = async function(id) {
  const input = document.getElementById('rename-' + id);
  const title = input.value.trim();
  if (!title) return;
  try {
    await fetch('/conversations/' + id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    input.value = '';
    loadConversations();
  } catch (err) {
    alert('Error: ' + err.message);
  }
};

window.deleteConv = async function(id) {
  if (!confirm('Delete this conversation?')) return;
  try {
    await fetch('/conversations/' + id, { method: 'DELETE' });
    if (conversationId === id) {
      conversationId = null;
      currentVersion = 0;
      viewedVersion = 0;
      appVersions = [];
      document.getElementById('conv-info').textContent = '';
      latestVersionBtn.classList.add('hidden');
            hidePreviewNotice();
      document.getElementById('chat-area').innerHTML =
        '<div class="chat-msg system"><div class="chat-bubble">Conversation deleted.</div></div>';
      placeholder.classList.remove('hidden');
      iframe.classList.add('hidden');
    }
    loadConversations();
  } catch (err) {
    alert('Error: ' + err.message);
  }
};

// ─── Helpers ──────────────────────────────────────────────────

function showStatus(text, kind = 'info') {
  const bar = document.getElementById('status-bar');
  if (statusTimer) {
    clearTimeout(statusTimer);
    statusTimer = null;
  }
  bar.classList.remove('hidden');
  bar.classList.remove('status-running', 'status-success', 'status-error');
  if (kind !== 'info') bar.classList.add(`status-${kind}`);
  bar.textContent = text;
}

function hideStatus() {
  if (statusTimer) {
    clearTimeout(statusTimer);
    statusTimer = null;
  }
  document.getElementById('status-bar').classList.add('hidden');
}

function flashStatus(text, kind = 'success', ms = 2400) {
  showStatus(text, kind);
  statusTimer = window.setTimeout(() => {
    statusTimer = null;
    if (!pendingAction) hideStatus();
  }, ms);
}

function showPreviewNotice(title, detail) {
  previewNotice.classList.remove('hidden');
  previewNotice.innerHTML = `<strong>${escHtml(title)}</strong><span>${escHtml(detail)}</span>`;
}

function hidePreviewNotice() {
  previewNotice.classList.add('hidden');
  previewNotice.innerHTML = '';
}

function setConversationInfo(primary, secondary = '') {
  const el = document.getElementById('conv-info');
  if (!primary) {
    el.textContent = '';
    return;
  }
  el.innerHTML = `<strong>${escHtml(primary)}</strong>${secondary ? `<span class="conv-pill">${escHtml(secondary)}</span>` : ''}`;
}

function hideSuggestions() {
  document.getElementById('suggestions-area').classList.add('hidden');
}

function setPending(value) {
  pendingAction = value;
  sendBtn.disabled = value;
  // Disable/enable suggestion buttons
  document.querySelectorAll('.suggestion-btn').forEach(b => {
    b.disabled = value;
    b.style.opacity = value ? '0.5' : '';
    b.style.pointerEvents = value ? 'none' : '';
  });
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escClass(s) {
  return String(s || '').replace(/[^a-zA-Z0-9_-]/g, '_');
}

function compactText(s, max = 500) {
  const text = String(s || '').replace(/\s+/g, ' ').trim();
  return text.length > max ? text.slice(0, max - 1) + '...' : text;
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function compactPath(value) {
  const path = String(value || '');
  const parts = path.split('/').filter(Boolean);
  if (parts.length <= 2) return path;
  return `.../${parts.slice(-2).join('/')}`;
}

function formatCodeSize(code) {
  const length = String(code || '').length;
  if (length >= 1000) return `${(length / 1000).toFixed(1)}k chars`;
  return `${length} chars`;
}

function adapterLabel(adapter) {
  if (adapter === 'codex_exec_resume') return 'Codex';
  if (adapter === 'openclaw_gateway') return 'OpenClaw';
  if (adapter === 'openclaw_taskflow') return 'OpenClaw TaskFlow';
  if (adapter === 'default') return 'HTTP';
  return adapter || 'Agent';
}

function runStatusLabel(status) {
  if (status === 'queued') return 'Queued';
  if (status === 'running') return 'Running';
  if (status === 'succeeded') return 'Completed';
  if (status === 'failed') return 'Failed';
  return status || 'Unknown';
}

function scrollChatToBottom() {
  const area = document.getElementById('chat-area');
  area.scrollTop = area.scrollHeight;
}

// Auto-load conversation if id is present in URL: /c/{id} or /?c={id}
(function () {
  const m = window.location.pathname.match(/^\/c\/([^/?#]+)/);
  const fromPath = m ? m[1] : null;
  const fromQuery = new URLSearchParams(window.location.search).get('c');
  const targetId = fromPath || fromQuery;
  if (targetId) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => window.loadConv(targetId));
    } else {
      window.loadConv(targetId);
    }
  }
})();
