<div align="center">

# SaC SDK

**The interaction layer between humans and agents.**

[![PyPI version](https://img.shields.io/pypi/v/sac-sdk.svg)](https://pypi.org/project/sac-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/sac-sdk.svg)](https://pypi.org/project/sac-sdk/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)

[Live demo](https://sac.dynsoft.ai) · [Paper](https://arxiv.org/abs/2603.21334) · [Architecture](./docs/architecture.md)

</div>

---

SaC is an open-source interaction layer that lets **any agent system**
communicate with the user through evolving interactive apps instead of plain
text. The agent doesn't reply with a chat message — it produces a runnable
app the user can click, type into, and reshape by talking back.

```
   ┌──────────────────────┐         skill / MCP / HTTP        ┌────────────────────┐
   │  Any Agent System    │ ───────────────────────────────►  │      SaC SDK       │
   │  Claude Code · Codex │                                   │  Interaction Layer │
   │  OpenClaw · custom   │ ◄───── user actions / events ──── │  (renders + routes)│
   └──────────────────────┘                                   └────────┬───────────┘
                                                                       │ HTTP + SSE
                                                                       ▼
                                                              ┌────────────────────┐
                                                              │ Browser (the user) │
                                                              │ clicks + types     │
                                                              │ in app + chat      │
                                                              └────────────────────┘
```

When your agent decides an interactive app is the right shape for a task, it
calls SaC and gets a URL. That URL stays live for the whole conversation —
the agent's later responses update the app in place (new versions, chat
bubbles), and the user's clicks/typing flow back to the agent through the
same surface. One URL = one ongoing conversation.

Where SaC sits in the stack:

- **Function calling** lets the agent *do things*
- **MCP** lets the agent *connect to external systems*
- **SaC** lets the agent *present an interactive surface to the user*

## Quick try

```bash
pip install sac-sdk
sac serve
```

Then open **http://0.0.0.0:18420** in your browser. The built-in playground
lets you generate apps from prompts and feel the loop without writing any code.

## Connect SaC to your agent

Three ways to plug SaC into an agent, depending on what your agent host supports.

### 1. MCP — for MCP-aware hosts (Claude Code)

The agent gets tools (`generate_app`, `evolve_app`, `wait_for_action`,
`send_chat`) and drives the loop natively. No separate server to manage —
the MCP host launches SaC on demand.

```bash
sac setup claude-code     # one-line install
```

→ [integrations/claude-code/](./integrations/claude-code/)

### 2. Skill — for skill-based agents (Codex, OpenClaw)

Install a skill file that teaches the agent how to POST to SaC's `/inbox`
and handle callbacks. The user starts `sac serve` manually; the agent
connects to it over HTTP.

```bash
sac serve                                                          # terminal 1
cp integrations/codex/SKILL.md ~/.codex/skills/sac-interaction/    # codex
cp integrations/openclaw/SKILL.md ~/.openclaw/workspace/skills/sac-interaction/  # openclaw
```

→ [integrations/codex/](./integrations/codex/) · [integrations/openclaw/](./integrations/openclaw/)

### 3. Library — embed in your Python agent loop

Use SaC as a Python library inside your own code. Most direct, lowest-level
integration. Currently best for prototyping — the ergonomics for full
production loops aren't polished yet.

```python
from sac import SaC
sac = SaC()
app = await sac.conversation().generate("3-day Tokyo itinerary")
# app.code is runnable TSX — render it however you want
```

The same loop, regardless of mode:

1. Agent opens a SaC conversation → gets a viewer URL (one per conversation)
2. User opens the URL, interacts with the rendered app
3. Click/type → SaC delivers the action back to the agent
4. Agent updates the same conversation → app evolves in place (new version
   in the iframe) or shows a chat bubble — no new URL

## When to use SaC

SaC shines when the value is in **how the user explores**, not in the final
deliverable. It's not the right answer for everything.

**✅ Good fit**

- **Exploration tasks** — trip planning, comparison shopping, research,
  project planning, financial reviews
- **Rich, varied agent outputs** that don't fit a fixed template — data
  analysis, multi-faceted plans, decision aids, internal-tool views

**❌ Skip SaC for**

- Simple Q&A or short conversational replies
- Strictly end-to-end task automation ("set an alarm for 7am")
- Socio-emotional conversations
- Open-ended *conceptual* exploration

If 95% of your agent's output is short text, you don't need SaC.

## Core ideas

### Conversation is your handle on an App's evolution

What persists, evolves, and gets shared is the **App** — a versioned artifact
with code, state, and affordances. **Conversation** is how that App evolves
through user actions and agent responses.

### Evolve ≠ Regenerate

When the user asks for a change, SaC inspects the current App, makes a
structured **growth decision** (extend the existing view vs add a new
section), then generates the change progressively. State and context are
preserved by design. This is what distinguishes SaC from one-shot UI
generators.

### Dual-channel UI

Every response has two channels: **Φˢ** (structured App version, rendered in
an iframe) and **Φⁿˡ** (natural-language chat reply, shown as a bubble). The
agent picks `type: "ui"` or `type: "chat"` for each response. Users can click
buttons OR type in the chat — both go back to the agent through the same
callback.

See the [paper](https://arxiv.org/abs/2603.21334) for the framing.

## Customize

Every layer is pluggable via Protocol classes:

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
Both are open-source — community contributions here are the highest-leverage
change you can make.

## Architecture (at a glance)

```
src/sac/
├── sac.py / conversation.py    Entry + Conversation primitive
├── runtime/                    Generate + Evolve pipeline, prompts, providers, store
├── server/
│   ├── http/                   FastAPI + /inbox + /action + SSE + viewer
│   └── mcp/                    MCP stdio server (embeds HTTP)
└── renderer/                   iframe sandbox + design system
```

Deeper notes: [`docs/architecture.md`](./docs/architecture.md).

## What SaC is NOT

- **Not a UI library** — no fixed components; the LLM generates structure
- **Not vibe coding** — SaC is for end-user agents, not developer IDE flows
- **Not GenUI** — GenUI picks from a component library; SaC generates the
  structure itself
- **Not a chat replacement** — SaC is a *parallel bandwidth* alongside chat

## Project status

`v0.15` — alpha. Core protocol is settling but may shift before `v1.0`. The
hosted product at [sac.dynsoft.ai](https://sac.dynsoft.ai) runs on the same
codebase, so production paths are battle-tested; the SDK boundary is what's
being polished.

## Contributing

Issues and PRs welcome. The highest-leverage changes right now are **prompt
improvements** in [`src/sac/runtime/prompts/`](./src/sac/runtime/prompts/) and
**design system contributions** in [`src/sac/renderer/design-systems/`](./src/sac/renderer/design-systems/).
For local dev: `pip install -e .`.

## Security

Found a vulnerability? Email **mulong@mulongxie.me** — please don't open a
public issue. SaC executes LLM-generated code in a sandboxed iframe, so
issues around iframe escape, prompt-injected exfiltration, or sandbox bypass
are especially in scope.

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
