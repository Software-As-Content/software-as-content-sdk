# SaC + Codex Integration

## Setup

### Option 1: Manual install

Copy the skill file to Codex's skills directory:

```bash
mkdir -p ~/.codex/skills/sac-interaction
cp integrations/codex/SKILL.md ~/.codex/skills/sac-interaction/SKILL.md
```

### Option 2: Let Codex install it

Give Codex the skill file and ask it to install:

```
Install this skill: /path/to/software-as-content-sdk/integrations/codex/SKILL.md
```

Codex will copy it to `~/.codex/skills/sac-interaction/SKILL.md` automatically.

### Verify

In a Codex session, the skill activates when you ask for interactive apps or dashboards. Example:

```
Analyze this repo and create an interactive release readiness dashboard using SaC.
```

## Prerequisites

- SaC server running: `sac serve` (from the SDK repo root)
- Default port: `18420`
