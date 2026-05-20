---
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

## Example

User: "Create a travel guide for Tokyo"

1. Read `~/.openclaw/openclaw.json` to get gateway token and port
2. Compose rich content about Tokyo (attractions, food, transport, tips)
3. Write content to temp file and POST to `http://127.0.0.1:18420/inbox`
4. Show the user the URL from the response
