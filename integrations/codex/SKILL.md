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

If `/inbox` is unreachable (connection refused), run `sac serve` **exactly
once** from the SDK repo root, then retry the same POST:

```bash
cd /path/to/software-as-content-sdk   # the SDK repo root
sac serve
```

`sac serve` is idempotent and safe to run even if a server is already
running — it reuses a healthy one and exits, and refuses to fight a
contended port instead of producing a half-bound zombie. If it still
fails, tell the user exactly: **"SaC server unavailable — start it from
the SDK repo with `sac serve`."** Then stop. Do not improvise.

## Server

SaC runs locally at `http://localhost:8000`. Use that URL. Start it from
the **SDK repo root** (not a subdirectory, not `~`): Codex callbacks
resolve `cwd=server` to the server's working directory, so a wrong launch
dir silently breaks the loop.

## New App

Fast path: do not over-investigate. Gather only the minimal context needed
to compose a useful workbench, then publish. Honor the infrastructure
boundary above — composing and POSTing content is the whole job.

Compose substantive markdown content first. Prefer structured sections, tables, risks, decisions, and next actions.

Then POST it to `/inbox`:

```bash
curl -s -X POST "http://localhost:8000/inbox" \
  -H "Content-Type: application/json" \
  -d '{"content": "CONTENT", "intent": "INTENT", "callback_url": "codex://resume?thread=last&cwd=server", "callback_format": "codex_exec_resume"}'
```

Fields:
- `CONTENT`: the engineering analysis to render.
- `INTENT`: short description, such as `SaC SDK release readiness dashboard`.
- `callback_url`: tells SaC how to send app button clicks back to Codex.
- `thread=last`: convenient default for a **single** Codex session. It
  resolves at click time to the most recent Codex thread — if other Codex
  sessions run between publish and the user's click, the callback resumes
  the wrong thread. For anything beyond a single-session demo, pass an
  explicit Codex thread id instead of `last`.
- `cwd=server`: resume Codex from the directory where `sac serve` is running. Use this default for SDK demos; do not put Codex artifact/session folders such as `~/Documents/Codex/...` in `cwd`. If you need a different repo, pass its URL-encoded absolute project root.

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
3. Use existing context first; avoid broad validation/debugging unless the action explicitly asks for it.
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
