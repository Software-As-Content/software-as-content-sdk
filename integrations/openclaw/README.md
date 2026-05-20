# SaC + OpenClaw Integration

## Setup

### 1. Install the skill

Copy the skill file to OpenClaw's skills directory:

```bash
mkdir -p ~/.openclaw/workspace/skills/sac-interaction
cp integrations/openclaw/SKILL.md ~/.openclaw/workspace/skills/sac-interaction/SKILL.md
```

### 2. Start both services

```bash
# Terminal 1: SaC server
sac serve

# Terminal 2: OpenClaw (must use gateway-connected mode)
openclaw tui
```

> **Important:** Use `openclaw tui`, not `openclaw terminal` (which runs locally and won't receive gateway callbacks).

### Verify

In an OpenClaw session, ask for an interactive app:

```
Create an interactive dashboard showing my project stats using SaC.
```

The agent will read `~/.openclaw/openclaw.json` for the gateway token automatically.

## How It Works

1. Agent sends content to SaC via `curl POST /inbox` with OpenClaw callback fields
2. SaC renders the app and returns a viewer URL
3. User opens the URL and interacts with the app (clicks buttons, submits forms)
4. SaC delivers actions back to the agent via WebSocket RPC (`sessions.send`) through the OpenClaw gateway
5. Agent receives the callback and sends updated content to evolve the app

## Prerequisites

- SaC server running: `sac serve` (default port: `18420`)
- OpenClaw gateway running: `openclaw tui`
