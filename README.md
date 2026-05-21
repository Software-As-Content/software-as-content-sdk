<div align="center">

# SaC SDK

### Interaction layer between you and your agents.

[![PyPI version](https://img.shields.io/pypi/v/sac-sdk.svg)](https://pypi.org/project/sac-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/sac-sdk.svg)](https://pypi.org/project/sac-sdk/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)

[Live demo](https://sac.dynsoft.ai) · [Paper](https://arxiv.org/abs/2603.21334)

</div>

---

SaC (Software as Content) is an **interaction layer** that gives your AI agent the ability to **generate and evolve interactive apps** as part of the conversation. Instead of replying with text or markdown, your agent builds a live React app — a dashboard, a planner, a comparison tool — and the user clicks, types, and explores. The agent then **evolves the same app** in response, preserving all context across turns.

This isn't one-shot UI generation. SaC apps are **stateful, conversational, and evolving** — the agent understands what the user is looking at, what they clicked, and grows the app from there. No existing agent can do this natively.

> **function calling** → agent *does things* &nbsp;·&nbsp;
> **MCP** → agent *talks to systems* &nbsp;·&nbsp;
> **SaC** → agent *shows, interacts, and evolves*

<!-- TODO: add demo GIF here -->

## Quickstart

### 1. Install

```bash
pip install sac-sdk
```

### 2. Configure your LLM

```bash
cp .env.example .env
```

Edit `.env` and add your API key. SaC uses an LLM to generate the apps — any OpenAI-compatible provider works:

```bash
# OpenRouter (default), Anthropic, OpenAI, Ollama, etc.
SAC_API_KEY=sk-or-v1-your-key-here

# Optional: custom endpoint for OpenAI direct, Ollama, vLLM, etc.
# SAC_API_BASE=https://api.openai.com/v1/chat/completions
```

### 3. Run

```bash
sac serve
```

Open **http://localhost:18420**, type *"3-day Tokyo trip planner with budget"*, and watch a live React app stream in. Click buttons. Ask it to evolve. This is SaC running a built-in agent loop — no external agent needed.

## Connect to your agent

SaC plugs into the agent you already use — through [MCP](#claude-code-mcp), [Skill](#codex-skill), or [code](#python-build-your-own-agent).

### Claude Code (MCP)

```bash
pip install sac-sdk
sac setup claude-code        # registers SaC as an MCP server
```

Restart Claude Code. Then try:

> *"Create an interactive release-readiness dashboard for this repo using SaC."*

Claude Code will generate the app, show you the URL, and enter the interaction loop automatically.

[Setup details →](./integrations/claude-code/)

### Codex (Skill)

```bash
pip install sac-sdk
sac setup codex              # installs the SaC skill
sac serve                    # keep running in a terminal
```

[Setup details →](./integrations/codex/)

### OpenClaw (Skill)

```bash
pip install sac-sdk
sac setup openclaw           # installs the SaC skill
sac serve                    # keep running in a terminal
```

[Setup details →](./integrations/openclaw/)

### Python (build your own agent)

```python
from sac import SaC

sac = SaC()
conv = sac.conversation()
app = await conv.generate("3-day Tokyo itinerary")
print(app.url)   # user opens this
# app.code contains the generated TSX
```

## How it works

```
Your agent ──▶ SaC ──▶ User sees a live app at a URL
                   ◀── User clicks a button / types a message
Your agent ──▶ SaC ──▶ Same URL, app evolves in place
                   ◀── ...
```

One URL, one conversation. The agent doesn't generate a new page every turn — it evolves the existing app. Users keep their context; the agent keeps its state.

**Two channels, one loop:** every response is either a UI update (the app evolves) or a chat reply (a text bubble). Users can click buttons in the app OR type in the chat — both go back to the agent through the same callback.

## When to use SaC

SaC is for tasks where **exploration and interaction** matter more than a final answer.

**Good fit:** trip planning, data analysis dashboards, comparison shopping, project planning, research, financial reviews, decision aids, internal tools

**Not the right tool for:** simple Q&A, one-shot automations ("set an alarm"), conversations that are purely text

## Customize

Every layer is pluggable:

```python
from sac import SaC, FileStore

sac = SaC(
    llm=YourLLMProvider(...),       # any class implementing LLMProvider
    search=YourSearchProvider(...), # any class implementing SearchProvider
    store=FileStore(".sac"),
)
```

Prompts live in [`src/sac/runtime/prompts/`](./src/sac/runtime/prompts/) and
the default design system is in [`src/sac/renderer/design-systems/default/`](./src/sac/renderer/design-systems/default/).

## Architecture

```
src/sac/
├── sac.py / conversation.py    Entry + Conversation primitive
├── runtime/                    Generate + Evolve pipeline, prompts, providers
├── server/
│   ├── http/                   FastAPI + SSE streaming + viewer
│   └── mcp/                    MCP stdio server (Claude Code integration)
└── renderer/                   iframe sandbox + design system
```

[Full architecture →](./docs/architecture.md)

## Project status

`v0.1.0` — alpha. The core protocol (generate → evolve → callback loop) is stable and runs in production at [sac.dynsoft.ai](https://sac.dynsoft.ai). The SDK surface is being polished toward v1.0.

## Contributing

Issues and PRs welcome. Highest-leverage contributions right now:
- **Prompt improvements** in [`src/sac/runtime/prompts/`](./src/sac/runtime/prompts/)
- **Design system contributions** in [`src/sac/renderer/design-systems/`](./src/sac/renderer/design-systems/)

For local dev: `pip install -e .`

## Citation

```bibtex
@article{xie2026sac,
  title  = {Software as Content: Dynamic Applications as the Human-Agent Interaction Layer},
  author = {Xie, Mulong},
  year   = {2026},
  url    = {https://arxiv.org/abs/2603.21334}
}
```

## License

[Apache-2.0](./LICENSE) · © 2026 Mulong Xie / Dynsoft Lab

---

<div align="center">

Built by [Dynsoft Lab](https://sac.dynsoft.ai). Questions: [mulong@mulongxie.me](mailto:mulong@mulongxie.me)

</div>
