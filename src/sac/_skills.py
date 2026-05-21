"""
Embedded SKILL.md content for agent platform integrations.

These are bundled in the package so `sac setup <platform>` works
after `pip install sac-sdk` — no need to clone the repo.
"""

from __future__ import annotations

# ── Codex SKILL.md ─────────────────────────────────────────────

CODEX_SKILL_MD = r"""---
name: sac-interaction
description: "Render interactive engineering workbenches via the SaC (Software as Content) interaction layer. Use when the user wants Codex analysis shown as an evolving interactive app."
metadata:
  {
    "codex":
      {
        "requires": { "bins": ["curl", "codex"] },
      },
  }
---

# SaC Interaction for Codex

Use SaC when Codex should present complex engineering analysis as an interactive app instead of a long markdown answer. The best Codex/SaC demos are developer workbenches: repo architecture maps, release readiness dashboards, PR/CI triage, migration plans, logs, test failures, and risk reviews.

Do not use SaC for short answers, simple code edits, or ordinary chat.

## Infrastructure boundary (read first)

SaC server lifecycle is **not your responsibility**. You are a publish
client, not an operator. Do **not**:

- restart, stop, or kill servers/processes
- change ports or migrate to a different port
- run test suites or debug unrelated infrastructure
- inspect or modify the repo unless the request explicitly asks for
  engineering analysis or code changes

If `/inbox` is unreachable (connection refused), follow this diagnostic
sequence:

**Step 1 — Connectivity check.** Run a lightweight health probe first:

```bash
curl -sS --connect-timeout 5 http://127.0.0.1:18420/health
```

If this returns `{"status":"ok"}`, the server IS running and `curl` GET
works. The POST failure is likely caused by payload construction, shell
quoting, `--data-binary @-` piping, or a POST-specific environment
restriction. Skip to **Step 3** to use a more robust transport.

If this also fails (connection refused), the server is truly down.
Continue to **Step 2**.

**Step 2 — Start the server.** Run `sac serve` **exactly once**:

```bash
sac serve
```

`sac serve` is idempotent and safe to run even if a server is already
running — it reuses a healthy one and exits, and refuses to fight a
contended port instead of producing a half-bound zombie. After `sac serve`,
retry the same POST with `curl`. If the retry succeeds, you are done.

**Step 3 — Python fallback.** If `curl` POST still fails but the health
check passed (or `sac serve` reported "already running and healthy"),
use Python `urllib` as an alternative transport. Write the full JSON
payload to a temporary file first so large markdown content with quotes,
backticks, and newlines is never shell-escaped:

```bash
python3 -c "
import urllib.request, json, os, sys
payload = json.dumps({
    'content': 'CONTENT',
    'intent': 'INTENT',
    'callback_url': f'codex://resume?thread=last&cwd={os.getcwd()}',
    'callback_format': 'codex_exec_resume',
})
req = urllib.request.Request('http://127.0.0.1:18420/inbox',
    data=payload.encode(), headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req, timeout=300)
print(resp.read().decode())
"
```

Replace `CONTENT` and `INTENT` with actual values.

If **both** curl and Python fallback fail, tell the user exactly:
**"SaC server unavailable — start it with `sac serve`."** Then stop.
Do not improvise.

## Server

SaC runs locally at `http://127.0.0.1:18420`. Use that URL.

## New App

Fast path: do not over-investigate. Gather only the minimal context needed
to compose a useful workbench, then publish. Honor the infrastructure
boundary above — composing and POSTing content is the whole job.

Compose substantive markdown content first. Prefer structured sections, tables, risks, decisions, and next actions.

**Publish in exactly one POST.** Do not send a smoke / probe / draft POST
to "test the endpoint" before the real content: the first POST becomes
app v1, so a throwaway draft pollutes the version history and doubles the
render cost. The `/inbox` endpoint is reliable — compose the complete
content, then POST it once. (`sac serve` health is already covered by the
infrastructure boundary above; do not re-verify with a tiny POST.)

Publish using the `sac publish` CLI. Write the content to a temp file
first — this avoids all shell-escaping issues with backticks, quotes, and
newlines in large markdown payloads:

```bash
cat > /tmp/sac_content.md << 'CONTENT_EOF'
CONTENT
CONTENT_EOF

sac publish --file /tmp/sac_content.md \
  --intent "INTENT" \
  --callback-url "codex://resume?thread=last&cwd=$(pwd)" \
  --callback-format codex_exec_resume
```

Replace `CONTENT` inside the heredoc with the actual markdown analysis,
and `INTENT` with a short description (e.g. `SaC SDK release readiness
dashboard`). The heredoc (`<< 'CONTENT_EOF'`) prevents shell expansion.

Fields:
- `--file`: path to the content file.
- `--intent`: short description of the content.
- `--callback-url`: tells SaC how to send app button clicks back to Codex.
- `thread=last`: safe bootstrap default. SaC auto-pins the concrete
  thread id after the first callback (it reads `thread.started` from the
  Codex stream and rewrites the stored callback_url), so every subsequent
  user action resumes this exact thread. The only residual race is if
  another Codex session starts between publish and the *first* click; if
  you already know your thread id, pass it explicitly as
  `thread=<id>` to close even that window.
- `cwd=$(pwd)`: resume Codex in your current working directory. The `$(pwd)` is expanded by the shell so Codex callbacks always return to the right project.

`sac publish` prints the app URL to stdout. Always show it to the user.

Keep the `conversation_id` (printed to stderr) for updates.

**Fallback:** if `sac publish` is not on `PATH`, use curl:

```bash
curl -s --connect-timeout 5 -X POST "http://127.0.0.1:18420/inbox" \
  -H "Content-Type: application/json" \
  -d "{\"content\": \"CONTENT\", \"intent\": \"INTENT\", \"callback_url\": \"codex://resume?thread=last&cwd=$(pwd)\", \"callback_format\": \"codex_exec_resume\"}"
```

## Update Existing App

For follow-up changes, publish updated content with the existing
`conversation_id`:

```bash
sac publish --file /tmp/sac_updated.md \
  --conversation-id "abc-123" \
  --intent "what changed"
```

Or with curl:

```bash
curl -s --connect-timeout 5 -X POST "http://127.0.0.1:18420/inbox" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "abc-123", "content": "UPDATED CONTENT", "intent": "what changed"}'
```

## Chat Reply (no UI change)

When the user's action is conversational — a greeting, question, clarification,
or small talk — do **not** evolve the app. Instead, POST a chat message:

```bash
cat > /tmp/sac_chat.json << 'CHAT_EOF'
{"conversation_id": "abc-123", "content": "YOUR_REPLY", "type": "chat"}
CHAT_EOF

curl -s --connect-timeout 5 -X POST "http://127.0.0.1:18420/inbox" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/sac_chat.json
```

This shows an assistant bubble in the viewer without touching the app UI.

## Handle SaC App Actions

When a user clicks a button or sends a message in the SaC app, SaC resumes
Codex with a message that starts:

```text
A user is viewing a SaC interactive app and requested: ...
```

Follow that message exactly:

1. Decide: does the request need a **UI change** (new analysis, fix, feature)
   or a **chat reply** (greeting, question, explanation)?
2. For UI changes → do the analysis, then publish updated content (see
   "Update Existing App" above) with the same `conversation_id`.
3. For chat replies → POST a chat message (see "Chat Reply" above).
4. Do not ask clarifying questions.
5. Use existing context first; avoid broad validation/debugging unless the
   action explicitly asks for it.
6. Your `content` and `intent` should describe WHAT to show — do NOT include
   UI styling directions (colors, dark/light theme, CSS classes, layout
   instructions). SaC controls visual design autonomously.

## Codex Demo Scenario

Use this as the primary B2D validation scenario:

```text
Analyze this SaC SDK and create an interactive release readiness dashboard using SaC.
```

The first app should include:
- architecture map
- integration status
- release blockers
- risks
- next tasks
- buttons such as `Inspect Codex integration path`, `Show release blockers`, and `Drill into callback adapters`

Buttons that need follow-up analysis should call:

```tsx
window.__sac_action("Inspect Codex integration path", {
  action_id: "inspect_codex_integration",
  target: { type: "integration", id: "codex" }
})
```
""".lstrip()


# ── OpenClaw SKILL.md ──────────────────────────────────────────

OPENCLAW_SKILL_MD = r"""---
name: sac-interaction
description: "Render interactive apps via the SaC (Software as Content) interaction layer. Use when the user wants to create, view, or interact with a visual UI, dashboard, or interactive page."
metadata:
  {
    "openclaw":
      {
        "emoji": "✦",
        "requires": { "bins": ["curl"] },
      },
  }
---

# SaC Interaction Skill

Render interactive apps via the SaC (Software as Content) interaction layer. SaC turns structured content (markdown, data) into rich, interactive web UIs.

## When to Use

**USE this skill when:**

- The user asks to create a visual UI, page, dashboard, or interactive app
- The user says "build me a ...", "show me a ...", "create a page for ..."
- The user wants to display data visually (charts, tables, guides, etc.)
- The user wants to update or evolve an existing SaC app
- You receive a message starting with "A user is viewing a SaC interactive app" (this is a callback from a rendered app — follow the instructions in the message)

**Do NOT use when:**

- The user just wants a text answer or chat reply
- The user wants to run a shell command or code locally

## Infrastructure boundary (read first)

SaC server lifecycle is **not your responsibility**. You are a publish
client, not an operator. Do **not**:

- restart, stop, or kill servers/processes
- change ports or migrate to a different port
- run test suites or debug unrelated infrastructure

If `/inbox` is unreachable (connection refused), tell the user:
**"SaC server unavailable — start it with `sac serve`."** Then stop.

## Server

SaC runs locally at **`http://127.0.0.1:18420`**. Always use this exact
URL and port. Do not use any other port.

## Setup (automatic, first time only)

Before your first SaC call, read the OpenClaw config to get the gateway token:

```
Read ~/.openclaw/openclaw.json
```

Extract `gateway.auth.token` and `gateway.port` (default 18789). You will need these for the `callback_url` and `callback_auth` fields below.

## New App

Compose substantive markdown content first. Prefer structured sections, tables, data, and actionable items.

**Publish in exactly one POST.** Do not send a probe / draft POST to
"test the endpoint" — the first POST becomes app v1.

Write content to a temp file to avoid shell-escaping issues:

```bash
cat > /tmp/sac_content.md << 'CONTENT_EOF'
YOUR MARKDOWN CONTENT HERE
CONTENT_EOF

cat > /tmp/sac_payload.json << PAYLOAD_EOF
{"content": "$(cat /tmp/sac_content.md | python3 -c "import sys,json; print(json.dumps(sys.stdin.read())[1:-1])")", "intent": "INTENT", "callback_url": "ws://127.0.0.1:GATEWAY_PORT?session=agent:main:main", "callback_format": "openclaw_gateway", "callback_auth": "Bearer GATEWAY_TOKEN"}
PAYLOAD_EOF

curl -s -X POST "http://127.0.0.1:18420/inbox" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/sac_payload.json
```

Where:
- **INTENT**: Short description of what you are creating.
- **GATEWAY_PORT**: From `gateway.port` in openclaw.json (default: 18789).
- **GATEWAY_TOKEN**: From `gateway.auth.token` in openclaw.json.

The response is JSON:
```json
{"conversation_id": "abc-123", "url": "http://127.0.0.1:18420/c/abc-123", "version": 1, "type": "ui"}
```

**Always show the user the `url` from the response so they can open it in their browser.**

Save the `conversation_id` — you need it for updates.

## Update Existing App

For follow-up changes, publish updated content with the existing `conversation_id`:

```bash
cat > /tmp/sac_content.md << 'CONTENT_EOF'
UPDATED CONTENT
CONTENT_EOF

cat > /tmp/sac_payload.json << PAYLOAD_EOF
{"conversation_id": "THE_SAVED_ID", "content": "$(cat /tmp/sac_content.md | python3 -c "import sys,json; print(json.dumps(sys.stdin.read())[1:-1])")", "intent": "what changed"}
PAYLOAD_EOF

curl -s -X POST "http://127.0.0.1:18420/inbox" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/sac_payload.json
```

Callback fields are only needed on the first call. Updates only need `conversation_id`, `content`, and `intent`.

## Chat Reply (no UI change)

When the user's action is conversational — a greeting, question, or
clarification — do **not** evolve the app. Instead, POST a chat message:

```bash
cat > /tmp/sac_chat.json << 'CHAT_EOF'
{"conversation_id": "abc-123", "content": "YOUR_REPLY", "type": "chat"}
CHAT_EOF

curl -s -X POST "http://127.0.0.1:18420/inbox" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/sac_chat.json
```

This shows an assistant bubble in the viewer without touching the app UI.

## Handle SaC App Actions

When a user clicks a button or sends a message in the SaC app, you will receive a message like:

```text
A user is viewing a SaC interactive app and requested: [action]
```

Follow that message:

1. Decide: does the request need a **UI change** (new analysis, fix, feature)
   or a **chat reply** (greeting, question, explanation)?
2. For UI changes → compose the requested content and publish an update
   (see "Update Existing App" above) with the same `conversation_id`.
3. For chat replies → POST a chat message (see "Chat Reply" above).
4. Do NOT ask clarifying questions — compose the best content you can and execute.
5. Your `content` and `intent` should describe WHAT to show — do NOT include
   UI styling directions (colors, dark/light theme, CSS classes, layout
   instructions). SaC controls visual design autonomously.

## Example

User: "Create a travel guide for Tokyo"

1. Read `~/.openclaw/openclaw.json` to get gateway token and port
2. Compose rich content about Tokyo (attractions, food, transport, tips)
3. Write content to temp file and POST to `http://127.0.0.1:18420/inbox`
4. Show the user the URL from the response
""".lstrip()


# ── Helpers ────────────────────────────────────────────────────

SKILL_TARGETS: dict[str, dict] = {
    "codex": {
        "content": CODEX_SKILL_MD,
        "dest": "~/.codex/skills/sac-interaction/SKILL.md",
        "label": "Codex",
    },
    "openclaw": {
        "content": OPENCLAW_SKILL_MD,
        "dest": "~/.openclaw/workspace/skills/sac-interaction/SKILL.md",
        "label": "OpenClaw",
    },
}
