import { SaCRenderer } from '/renderer/sac-renderer.js';

// ─── Renderer setup ───────────────────────────────────────────

const iframe = document.getElementById('preview');
const placeholder = document.getElementById('placeholder');
const previewNotice = document.getElementById('preview-notice');
const showChangesBtn = document.getElementById('show-changes-btn');
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

// ─── Show Changes button ─────────────────────────────────────

let _changeIndex = 0;   // cycles through highlighted elements
let _changeCount = 0;

showChangesBtn.addEventListener('click', () => {
  const iframeWin = iframe.contentWindow;
  if (!iframeWin) return;
  iframeWin.postMessage({ type: 'scroll-to-change', index: _changeIndex }, '*');
  _changeIndex++;
});

// Listen for change-count and visibility updates from iframe
window.addEventListener('message', (ev) => {
  if (ev.data?.type === 'sac-change-count') {
    _changeCount = ev.data.count || 0;
    if (_changeCount > 0) {
      showChangesBtn.textContent = `Show Changes (${_changeCount})`;
      showChangesBtn.classList.remove('hidden');
      _changeIndex = 0;
    } else {
      showChangesBtn.classList.add('hidden');
    }
  }
  if (ev.data?.type === 'sac-highlights-visible') {
    if (!ev.data.visible && _changeCount > 0) {
      // Highlights dismissed — update button text
      showChangesBtn.textContent = `Show Changes (${_changeCount})`;
      _changeIndex = 0;
    }
  }
});

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

// ─── Streaming preview state ────────────────────────────────
// Matches the product's approach: accumulate chunks in a buffer,
// throttle-flush to the iframe with silent=true. No autoClose or
// parent-side Babel gate — the iframe's own Babel decides; failures
// are silenced and the last good frame stays visible.
let streamBuffer = '';
let streamFlushTimer = null;
const STREAM_FLUSH_MS = 150;
let pendingSearchSources = [];   // search results accumulated during a generation cycle
let pendingStages = [];          // stage events accumulated during a generation cycle

function streamPush(chunk) {
  if (!streamBuffer) {
    // First chunk — ensure iframe is loaded before we try to render into it
    renderer._ensureIframe();
  }
  streamBuffer += chunk;
  if (!streamFlushTimer) {
    streamFlushTimer = setTimeout(streamFlush, STREAM_FLUSH_MS);
  }
}

function streamFlush() {
  streamFlushTimer = null;
  if (!streamBuffer) return;
  // Strip fences and rewrite imports. The iframe's own repairPartialTsx +
  // render scheduler handles partial code repair and last-good-frame fallback.
  const processed = renderer._processCode(streamBuffer);
  if (processed && processed.trim()) {
    renderer._sendToIframe(processed, true);
  }
}

function streamEnd() {
  if (streamFlushTimer) {
    clearTimeout(streamFlushTimer);
    streamFlushTimer = null;
  }
  if (streamBuffer) {
    // Final render with full code — non-silent so errors surface
    renderer.render(streamBuffer);
  }
  streamBuffer = '';
}

function streamReset() {
  if (streamFlushTimer) {
    clearTimeout(streamFlushTimer);
    streamFlushTimer = null;
  }
  streamBuffer = '';
}

// ─── Sidebar tab switching ───────────────────────────────────

document.querySelectorAll('.sidebar .tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.sidebar .tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.sidebar .tab-content').forEach(c => c.classList.add('hidden'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.remove('hidden');
    if (tab.dataset.tab === 'conversations') loadConversations();
  });
});

// ─── Preview tab switching (App / Code) ─────────────────────

const previewCodePanel = document.getElementById('preview-code-panel');

document.querySelectorAll('.preview-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.preview-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const mode = tab.dataset.ptab;
    if (mode === 'code') {
      iframe.classList.add('hidden');
      placeholder.classList.add('hidden');
      previewCodePanel.classList.remove('hidden');
    } else {
      previewCodePanel.classList.add('hidden');
      // Show iframe or placeholder depending on state
      if (viewedVersion > 0) {
        iframe.classList.remove('hidden');
      } else {
        placeholder.classList.remove('hidden');
      }
    }
  });
});

// ─── Sidebar toggle ─────────────────────────────────────────

document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.querySelector('.sidebar').classList.toggle('collapsed');
});

// ─── Send handler (unified entry point) ──────────────────────

const sendBtn = document.getElementById('send-btn');
const intentInput = document.getElementById('intent');
const codeDisplay = document.getElementById('code-display');
const codeMeta = document.getElementById('code-meta');
const copyCodeBtn = document.getElementById('copy-code-btn');
sendBtn.addEventListener('click', () => handleSend());
intentInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
});
// "Back to Latest" now handled programmatically — no header button
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

    // Finalize any in-progress stream before applying the version.
    streamReset();

    // New App version pushed by an agent — fetch latest code and re-render.
    try {
      const res = await fetch('/conversations/' + convId);
      const { conversation, events = [] } = await res.json();
      if (conversation && conversation.latest_code) {
        appVersions = extractAppVersions(events);
        const latest = appVersions[appVersions.length - 1];
        currentVersion = latest?.version || data.version || currentVersion;
        if (latest) {
          if (pendingSearchSources.length > 0) {
            latest.sources = [...(latest.sources || []), ...pendingSearchSources];
            pendingSearchSources = [];
          }
          if (pendingStages.length > 0) {
            latest.stages = [...(latest.stages || []), ...pendingStages];
            pendingStages = [];
          }
          ensureVersionCard(latest);
          applyAppVersion(latest, { announce: true });
        } else {
          // conv info removed from header
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
    } else if (data.status === 'no_update') {
      flashStatus(`${adapterLabel(data.adapter)} finished — app unchanged`, 'error');
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

  // ─── Streaming events (from /inbox generation) ──────────────

  es.addEventListener('stage', (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    showStatus(`${data.name}: ${data.status}`, 'running');
    if ((data.status === 'complete' || data.status === 'success') && data.duration) {
      pendingStages.push({ name: data.name, duration: data.duration });
    }
  });

  es.addEventListener('search', (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    for (const r of (data.results || [])) {
      for (const src of (r.sources || [])) {
        pendingSearchSources.push({ title: src.title || src.url, url: src.url, query: r.query });
      }
    }
    if (data.results?.length > 0) {
      showStatus(`Searched: ${data.results.map(r => r.query).join(', ')}`, 'running');
    }
  });

  es.addEventListener('chunk', (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    const chunk = data.data;
    if (!chunk) return;

    // First chunk: prepare the UI for streaming
    if (!streamBuffer) {
      placeholder.classList.add('hidden');
      iframe.classList.remove('hidden');
      codeDisplay.textContent = '';
      codeMeta.textContent = 'Streaming generated code...';
      showStatus('Generating...', 'running');
    }
    codeDisplay.textContent += chunk;
    streamPush(chunk);
  });

  es.addEventListener('snapshot', (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    const code = data.code;
    if (!code) return;

    // First snapshot: prepare UI
    if (!streamBuffer) {
      placeholder.classList.add('hidden');
      iframe.classList.remove('hidden');
      codeMeta.textContent = 'Applying changes...';
      showStatus('Evolving...', 'running');
    }

    // REPLACE buffer (not append) — snapshot is the full updated code
    streamBuffer = code;
    codeDisplay.textContent = code;

    // Flush to iframe immediately with scroll-to-change flag
    if (streamFlushTimer) {
      clearTimeout(streamFlushTimer);
      streamFlushTimer = null;
    }
    const processed = renderer._processCode(code);
    if (processed && processed.trim()) {
      renderer._ensureIframe();
      iframe.contentWindow?.postMessage({
        type: 'render',
        code: processed,
        shimUrl: renderer._designSystem,
        silent: true,
        scrollToChange: true,
      }, '*');
    }
  });

  es.addEventListener('error', (e) => {
    // Server-sent error event (not SSE connection error)
    let data;
    try { data = JSON.parse(e.data); } catch { return; }
    streamReset();
    showStatus('Error: ' + (data.error || 'unknown'), 'error');
    addChatMsg('system', 'Error: ' + (data.error || 'unknown'));
    setPending(false);
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

  streamReset();

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
            handleSSEEvent(currentEvent, data);
          } catch {}
          currentEvent = null;
        }
      }
    }
  } catch (err) {
    showStatus('Connection error: ' + err.message, 'error');
    streamReset();
    setPending(false);
  }
}

function handleSSEEvent(eventType, data) {
  switch (eventType) {
    case 'stage':
      showStatus(`${data.name}: ${data.status}`, 'running');
      if (data.status === 'complete' || data.status === 'success') {
        pendingStages.push({ name: data.name, duration: data.duration });
      }
      break;

    case 'search': {
      const results = data.results || [];
      for (const r of results) {
        for (const src of (r.sources || [])) {
          pendingSearchSources.push({ title: src.title || src.url, url: src.url, query: r.query });
        }
      }
      if (results.length > 0) {
        showStatus(`Searched: ${results.map(r => r.query).join(', ')}`, 'running');
      }
      break;
    }

    case 'snapshot': {
      // Progressive evolve: full code snapshot replaces buffer
      streamBuffer = data.code;
      codeDisplay.textContent = data.code;
      if (streamFlushTimer) { clearTimeout(streamFlushTimer); streamFlushTimer = null; }
      const proc = renderer._processCode(data.code);
      if (proc && proc.trim()) {
        renderer._ensureIframe();
        iframe.contentWindow?.postMessage({
          type: 'render',
          code: proc,
          shimUrl: renderer._designSystem,
          silent: true,
          scrollToChange: true,
        }, '*');
      }
      break;
    }

    case 'chunk': {
      let chunk = data.data;
      // Display raw in code panel
      codeDisplay.textContent += chunk;
      // Accumulate in stream buffer — throttled flush to iframe
      streamPush(chunk);
      break;
    }

    case 'complete': {
      // Final render with the authoritative code from the complete event
      streamReset();
      const app = data.app;
      renderer.render(app.code);

      if (data.conversation_id) conversationId = data.conversation_id;
      currentVersion = app.version;
      const stagesData = (app.stages || []).length > 0 ? app.stages : pendingStages;
      const version = {
        version: app.version,
        title: app.intent || `Version ${app.version}`,
        code: app.code,
        kind: app.parent_version ? 'evolved' : 'generated',
        createdAt: app.created_at,
        sources: [...pendingSearchSources],
        stages: stagesData,
      };
      pendingSearchSources = [];
      pendingStages = [];
      upsertAppVersion(version);

      // Update header
      applyAppVersion(version);

      // Show completion in chat
      ensureVersionCard(version);

      // Show suggestions
      renderSuggestions(app.suggestions || []);

      const stagesSummary = (stagesData || []).map(s =>
        `${s.name}: ${s.duration ? s.duration.toFixed(1) + 's' : s.status}`
      ).join(' → ');
      flashStatus(stagesSummary || `App updated to v${version.version}`, 'success');
      setPending(false);
      break;
    }

    case 'error':
      showStatus('Error: ' + data.error, 'error');
      addChatMsg('system', 'Error: ' + data.error);
      streamReset();
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
  let pendingSources = [];
  for (const event of events || []) {
    if (event.type === 'search' && event.status === 'success') {
      for (const r of (event.results || [])) {
        for (const src of (r.sources || [])) {
          pendingSources.push({ title: src.title || src.url, url: src.url });
        }
      }
    }
    if ((event.type === 'generation' || event.type === 'growth') && event.status === 'success' && event.code) {
      versions.push({
        version: versions.length + 1,
        title: event.intent || `Version ${versions.length + 1}`,
        code: event.code,
        kind: event.type === 'generation' ? 'generated' : 'evolved',
        createdAt: event.timestamp,
        suggestions: event.intent_suggestions || [],
        sources: [...pendingSources],
        stages: event.stages || [],
      });
      pendingSources = [];
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
  // Ensure App tab is active in preview
  previewCodePanel.classList.add('hidden');
  placeholder.classList.add('hidden');
  iframe.classList.remove('hidden');
  document.querySelectorAll('.preview-tab').forEach(t => t.classList.toggle('active', t.dataset.ptab === 'app'));
  hidePreviewNotice();
  renderer.render(version.code);
  markActiveVersionCard(version.version);
    if (opts.announce) {
    addChatMsg('system', `App updated to v${version.version}`);
    flashStatus(`App updated to v${version.version}`, 'success');
    flashVersionCard(version.version);
  }
}

function ensureVersionCard(version) {
  const area = document.getElementById('chat-area');
  const id = `version-card-${version.version}`;
  let wrapper = document.getElementById(id);
  if (!wrapper) {
    wrapper = document.createElement('div');
    wrapper.id = id;
    wrapper.className = 'version-card';
    area.appendChild(wrapper);
  }
  const kindLabel = version.kind === 'generated' ? 'generated' : 'evolved';
  const timeStr = version.createdAt ? formatTime(version.createdAt) : '';
  const sources = version.sources || [];
  const stages = version.stages || [];
  const hasDetails = sources.length > 0 || stages.length > 0;

  let detailsHtml = '';
  if (hasDetails) {
    const sourcesHtml = sources.length > 0 ? `
      <div class="vc-detail-section">
        <div class="vc-detail-toggle" data-section="sources">
          <span class="vc-detail-arrow">›</span>
          Sources (${sources.length})
        </div>
        <div class="vc-detail-body" data-section-body="sources">
          ${sources.slice(0, 10).map(s => `<div class="vc-source-item">${s.url ? `<a href="${escHtml(s.url)}" target="_blank" rel="noopener">${escHtml(compactText(s.title || s.url, 60))}</a>` : escHtml(compactText(s.title, 60))}</div>`).join('')}
          ${sources.length > 10 ? `<div class="vc-source-item" style="color:#a8a29e;">+${sources.length - 10} more</div>` : ''}
        </div>
      </div>` : '';

    const stagesHtml = stages.length > 0 ? `
      <div class="vc-detail-section">
        <div class="vc-detail-toggle" data-section="stages">
          <span class="vc-detail-arrow">›</span>
          Pipeline (${stages.length} stages)
        </div>
        <div class="vc-detail-body" data-section-body="stages">
          ${stages.map(s => `<div class="vc-stage-item"><span class="vc-stage-name">${escHtml(s.name)}</span>${s.duration ? `<span class="vc-stage-dur">${s.duration.toFixed(1)}s</span>` : ''}</div>`).join('')}
        </div>
      </div>` : '';

    detailsHtml = `<div class="vc-details">${sourcesHtml}${stagesHtml}</div>`;
  }

  wrapper.innerHTML = `
    <div class="vc-header">
      <span class="version-card-badge">v${version.version}</span>
      <span class="version-card-title">${escHtml(version.title || `Version ${version.version}`)}</span>
      <span class="version-card-kind">${escHtml(kindLabel)}${timeStr ? ' · ' + escHtml(timeStr) : ''}</span>
    </div>
    ${detailsHtml}
  `;

  // Click header to switch version
  wrapper.querySelector('.vc-header').addEventListener('click', () => applyAppVersion(version));

  // Toggle detail sections
  wrapper.querySelectorAll('.vc-detail-toggle').forEach(toggle => {
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      const section = toggle.dataset.section;
      const body = wrapper.querySelector(`[data-section-body="${section}"]`);
      const arrow = toggle.querySelector('.vc-detail-arrow');
      if (body.classList.contains('expanded')) {
        body.classList.remove('expanded');
        arrow.textContent = '›';
      } else {
        body.classList.add('expanded');
        arrow.textContent = '⌄';
      }
    });
  });

  markActiveVersionCard(viewedVersion);
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

function renderCallbackRun(run) {
  const shortId = (run.id || '').slice(0, 8);
  const card = ensureCallbackCard(run);
  const status = run.status || 'unknown';
  const title = card.el.querySelector('.callback-card-title');
  const subtitle = card.el.querySelector('.callback-card-subtitle');
  const meta = card.el.querySelector('.callback-card-meta');
  const statusEl = card.el.querySelector('.callback-status');

  card.el.className = `callback-card ${escClass(status)}${card.el.classList.contains('expanded') ? ' expanded' : ''}`;
  title.textContent = `${adapterLabel(run.adapter)}`;
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
          <div class="callback-card-title">${escHtml(adapterLabel(run.adapter))}</div>
          <div class="callback-card-subtitle">Waiting for agent activity</div>
          <div class="callback-card-meta">#${escHtml((run.id || '').slice(0, 8))}</div>
        </div>
      </div>
      <span class="callback-status ${escClass(run.status || 'queued')}">${escHtml(runStatusLabel(run.status || 'queued'))}</span>
    </div>
    <div class="callback-events"></div>`;
  el.querySelector('.callback-card-header').addEventListener('click', () => {
    el.classList.toggle('expanded');
  });
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
    // conv info display removed from header
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
  if (status === 'no_update') return 'No update';
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
