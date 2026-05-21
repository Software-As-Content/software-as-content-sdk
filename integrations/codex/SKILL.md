---
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
