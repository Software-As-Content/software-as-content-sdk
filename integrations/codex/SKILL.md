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

## Server

SaC runs locally at `http://localhost:8000` by default.

If needed, start it from the SDK repo:

```bash
sac serve --port 8000
```

## New App

Compose substantive markdown content first. Prefer structured sections, tables, risks, decisions, and next actions.

Then POST it to `/inbox`:

```bash
curl -s -X POST "http://localhost:8000/inbox" \
  -H "Content-Type: application/json" \
  -d '{"content": "CONTENT", "intent": "INTENT", "callback_url": "codex://resume?thread=last&cwd=CWD_URL_ENCODED", "callback_format": "codex_exec_resume"}'
```

Fields:
- `CONTENT`: the engineering analysis to render.
- `INTENT`: short description, such as `SaC SDK release readiness dashboard`.
- `callback_url`: tells SaC how to send app button clicks back to Codex.
- `thread=last`: fastest local default. Use an explicit Codex thread id when known.
- `cwd`: optional URL-encoded working directory. If omitted, Codex resumes from its stored thread cwd.

Always show the returned `url` to the user.

Example response:

```json
{"conversation_id":"abc-123","url":"http://localhost:8000/c/abc-123","version":1,"type":"ui"}
```

Keep the `conversation_id` for updates.

## Update Existing App

For follow-up changes, POST updated content with the existing `conversation_id`:

```bash
curl -s -X POST "http://localhost:8000/inbox" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "abc-123", "content": "UPDATED CONTENT", "intent": "what changed"}'
```

## Handle SaC App Actions

When a user clicks a button in the SaC app, SaC resumes Codex with a message that starts:

```text
A user is viewing a SaC interactive app and requested: ...
```

Follow that message exactly:

1. Continue the requested analysis.
2. Do not ask clarifying questions.
3. Compose the best updated content you can.
4. Run the provided `curl -s -X POST ... /inbox` command with the same `conversation_id`.

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

