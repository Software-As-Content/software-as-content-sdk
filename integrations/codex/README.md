# SaC + Codex Integration

SaC connects to Codex via a skill file. Codex uses the skill to POST content to
SaC's `/inbox` endpoint, and SaC delivers user actions back via `codex exec resume`.

## Setup

### Option 1: Manual install

```bash
mkdir -p ~/.codex/skills/sac-interaction
cp integrations/codex/SKILL.md ~/.codex/skills/sac-interaction/SKILL.md
```

### Option 2: Let Codex install it

Give Codex the skill file path and ask it to install:

```
Install this skill: /path/to/software-as-content-sdk/integrations/codex/SKILL.md
```

Codex will copy it to `~/.codex/skills/sac-interaction/SKILL.md` automatically.

### Remove

```bash
rm -rf ~/.codex/skills/sac-interaction
```

## Verify

Start the SaC server, then in a Codex session try:

```
Analyze this repo and create an interactive release readiness dashboard using SaC.
```

The skill activates when you ask for interactive apps or dashboards. Codex
will POST to SaC and print the viewer URL.

## How It Works

1. Codex composes markdown content and POSTs to `/inbox` via `sac publish` CLI
2. SaC renders the app and returns a viewer URL
3. User opens the URL and interacts with the app (clicks buttons, types messages)
4. SaC dispatches the action back to Codex via `codex exec resume` with the original thread
5. Codex either evolves the app (POST new content) or replies via chat (POST `type: "chat"`)

The skill teaches Codex when to evolve vs. chat, how to handle the callback,
and how to fall back to `python urllib` if curl POST fails in Codex's sandbox.
