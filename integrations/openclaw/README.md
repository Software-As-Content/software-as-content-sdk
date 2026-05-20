# SaC + OpenClaw Integration

SaC connects to OpenClaw via a skill file. OpenClaw POSTs content to SaC's
`/inbox` endpoint, and SaC delivers user actions back via WebSocket RPC
through the OpenClaw gateway.

## Setup

```bash
mkdir -p ~/.openclaw/workspace/skills/sac-interaction
cp integrations/openclaw/SKILL.md ~/.openclaw/workspace/skills/sac-interaction/SKILL.md
```

Then start both services:

```bash
# Terminal 1: SaC server
sac serve

# Terminal 2: OpenClaw (must use gateway-connected mode)
openclaw tui
```

> **Important:** Use `openclaw tui`, not `openclaw terminal` (which runs locally and won't receive gateway callbacks).

### Remove

```bash
rm -rf ~/.openclaw/workspace/skills/sac-interaction
```

## Verify

In an OpenClaw session, ask for an interactive app:

```
Create an interactive dashboard showing my project stats using SaC.
```

The agent will read `~/.openclaw/openclaw.json` for the gateway token automatically.

## How It Works

1. Agent POSTs content to SaC's `/inbox` with OpenClaw callback fields (gateway URL + auth token)
2. SaC renders the app and returns a viewer URL
3. User opens the URL and interacts with the app (clicks buttons, submits forms)
4. SaC delivers actions back to the agent via WebSocket RPC (`sessions.send`) through the OpenClaw gateway
5. Agent receives the callback and POSTs updated content to evolve the app
