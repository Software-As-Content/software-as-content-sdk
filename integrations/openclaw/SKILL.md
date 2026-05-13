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

## Setup (automatic, first time only)

Before your first SaC call, read the OpenClaw config to get the gateway token:

```
Read ~/.openclaw/openclaw.json
```

Extract `gateway.auth.token` and `gateway.port` (default 18789). You will need these for the `callback_url` and `callback_auth` fields below.

The SaC server runs at `http://localhost:8000` by default. If it is running elsewhere, the user will tell you.

## How to Execute

**IMPORTANT: Use `exec` to run `curl` commands. Do NOT try to call any tool named `sac_interaction` or `sac_inbox` — they do not exist.**

### Step 1: Prepare your content

Compose rich, substantive content for the app. Include real data, structured sections, markdown formatting. The more detailed and structured, the better the rendered app.

### Step 2: Send to SaC (first time — new app)

Use `exec` to run this curl command. Replace CONTENT and INTENT with your actual values:

```
exec: curl -s -X POST "http://localhost:8000/inbox" -H "Content-Type: application/json" -d '{"content": "CONTENT", "intent": "INTENT", "callback_url": "ws://127.0.0.1:GATEWAY_PORT?session=agent:main:main", "callback_format": "openclaw_gateway", "callback_auth": "Bearer GATEWAY_TOKEN"}'
```

Where:
- **CONTENT**: Your composed content (markdown). Escape quotes and newlines for JSON.
- **INTENT**: Short description of what you are creating.
- **GATEWAY_PORT**: From `gateway.port` in openclaw.json (default: 18789).
- **GATEWAY_TOKEN**: From `gateway.auth.token` in openclaw.json.

The response is JSON:
```json
{"conversation_id": "abc-123", "url": "http://localhost:8000/c/abc-123", "version": 1, "type": "ui"}
```

**Always show the user the `url` from the response so they can open it in their browser.**

Save the `conversation_id` — you need it for updates.

### Step 3: Update an existing app

When the user asks for changes, or when you receive a callback message from a rendered app, include the `conversation_id`:

```
exec: curl -s -X POST "http://localhost:8000/inbox" -H "Content-Type: application/json" -d '{"conversation_id": "THE_SAVED_ID", "content": "UPDATED CONTENT", "intent": "what changed"}'
```

Note: callback fields are only needed on the first call. Updates only need `conversation_id`, `content`, and `intent`.

### Step 4: Handle user actions from the app

When a user interacts with a rendered SaC app (clicks buttons, submits forms), you will receive a message like:

> A user is viewing a SaC interactive app and requested: [action]
> ...
> exec: curl -s -X POST "http://localhost:8000/inbox" ...

**Follow the instructions in the message.** Compose the requested content and run the curl command. Do NOT ask clarifying questions — just compose the best content you can and execute.

## Content Guidelines

- **Be substantive**: Provide real data, detailed text, structured information — not placeholder content.
- **Structure helps**: Use markdown headings, lists, tables, and sections.
- **Escape JSON properly**: The content field is a JSON string. Escape quotes and newlines.
- **Always use exec**: Every curl command must be run via the `exec` tool.

## Example

User: "Create a travel guide for Tokyo"

1. Read `~/.openclaw/openclaw.json` to get gateway token and port
2. Compose rich content about Tokyo (attractions, food, transport, tips)
3. Run:

```
exec: curl -s -X POST "http://localhost:8000/inbox" -H "Content-Type: application/json" -d '{"content": "# Tokyo Travel Guide\n\n## Top Attractions\n1. **Senso-ji Temple** - Tokyo oldest temple in Asakusa...\n2. **Shibuya Crossing** - The world famous scramble crossing...\n\n## Local Food\n- **Ramen** - Try Fuunji in Shinjuku for tsukemen...\n- **Sushi** - Tsukiji Outer Market for fresh morning sushi...\n\n## Getting Around\n- Get a Suica/Pasmo IC card for trains and buses\n- Tokyo Metro and JR Yamanote line cover most tourist areas", "intent": "Tokyo travel guide", "callback_url": "ws://127.0.0.1:18789?session=agent:main:main", "callback_format": "openclaw_gateway", "callback_auth": "Bearer YOUR_TOKEN_HERE"}'
```

4. Show the user the URL from the response.
