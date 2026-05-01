<div align="center">

# SaC SDK

**Conversations that produce evolving software.**

[![PyPI version](https://img.shields.io/pypi/v/sac-sdk.svg)](https://pypi.org/project/sac-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/sac-sdk.svg)](https://pypi.org/project/sac-sdk/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)

[Live demo](https://sac.dynsoft.ai) · [Paper](https://arxiv.org/abs/2603.21334) · [MCP setup](./docs/mcp.md) · [Embedding](./docs/embedding.md)

</div>

---

Software as Content (SaC) is an open-source SDK that gives any agent the
ability to **generate and evolve interactive applications through
conversation**. The agent doesn't reply with text or pick from a fixed
component library — it produces a runnable app, and the user evolves it by
talking back.

The unit isn't a one-shot UI generation. It's a **Conversation** that produces
a stream of evolving App versions, each one a snapshot the user can interact
with, refine, or replace.

## When to use SaC

SaC shines when the value is in **how the user explores**, not in the final
deliverable. It's not the right answer for everything.

**✅ Good fit**

- **Exploration tasks** where the user discovers what they want by interacting
  — trip planning, comparison shopping, research, project planning, financial
  reviews
- **Rich, varied agent outputs** that don't fit a fixed template — data
  analysis, multi-faceted plans, decision aids, internal-tool views

**❌ Skip SaC for**

- Simple Q&A or short conversational replies — text is fine
- Strictly end-to-end task automation ("set an alarm for 7am") — no UI needed
- Socio-emotional conversations — the right shape is dialog, not an app
- Open-ended *conceptual* exploration ("am I approaching my work the wrong
  way") — generated UI gets in the way

If 95% of your agent's output is short text, you don't need SaC. We'd rather
say so up front.

## Quickstart

```bash
pip install sac-sdk[server]
export SAC_API_KEY="sk-or-..."        # OpenRouter key
```

```python
import asyncio
from sac import SaC

async def main():
    sac = SaC()
    conv = sac.conversation()                                       # Conversation is your handle
    app = await conv.generate("3-day Tokyo itinerary")
    app = await conv.evolve("add restaurant picks for each day")    # not regenerate — evolve
    print(f"v{app.version} • {len(app.code):,} chars • {app.growth_decision.growth_type}")

asyncio.run(main())
```

To see what you generated:

```bash
sac serve     # opens a playground at http://localhost:8000
```

Pick your conversation from the sidebar.

## Four ways to use SaC

Different builders need different surfaces. The same SDK serves all four.

### 🎮 Try it · `sac serve`

Local playground with chat, render, conversation history, and an API explorer.
The fastest way to feel SaC.

```bash
pip install sac-sdk[server]
sac serve
```

### 🐍 Library mode · `import sac`

Embed SaC inside your own Python agent loop. The most common path for builders
on LangGraph, CrewAI, Mastra, Claude Agent SDK, or hand-written loops.

```python
from sac import SaC
sac = SaC(api_key="sk-...")
app = await sac.conversation().generate("research brief on …")
# app.code is runnable TSX you render in your frontend
```

See [`examples/agents/`](./examples/agents/) for the four common integration
patterns.

### 🔌 MCP mode · `sac serve --transport stdio`

Plug SaC into any MCP-aware host (Claude Desktop, Cursor, Cline, custom). The
agent gets four tools: `generate_app`, `evolve_app`, `list_conversations`,
`get_conversation`. No code changes needed in the host.

```bash
pip install sac-sdk[mcp]
sac serve --transport stdio
```

Full setup including Claude Desktop config: [`docs/mcp.md`](./docs/mcp.md).

### 🌐 HTTP/SSE mode · `sac serve` + your frontend

Use the FastAPI server as a backend for your own webapp. Token-level streaming
via SSE, conversation CRUD, multi-user via headers. This is how the hosted
product at [sac.dynsoft.ai](https://sac.dynsoft.ai) is built.

See [`docs/frontend-integration.md`](./docs/frontend-integration.md) for the
full HTTP / SSE contract.

## Core concepts

### Conversation is your handle on an App's evolution chain

What persists, evolves, and gets shared is the **App** — a versioned artifact
with code, state, and affordances. **Conversation** is the SDK's primary entry
point for driving that evolution through natural language.

Hold onto a `Conversation`. The App is what you're building.

```python
conv = sac.conversation()       # ← you hold this
app = await conv.generate(...)  # snapshot v1
app = await conv.evolve(...)    # snapshot v2 (not a fresh generation!)
app = await conv.evolve(...)    # snapshot v3
print(conv.version, len(conv.history))
```

In the future, other drivers (structured affordances, environmental events,
multi-agent signals) will join Conversation as parallel ways to evolve the
same App. The SDK is designed so that adding them later won't break this API.

### Evolve ≠ Regenerate

`conv.evolve(intent)` is not "throw the previous code back at the LLM". SaC
inspects the current App, makes a structured **growth decision** (extend the
existing view vs add a new section), then generates the change. State and
context are preserved by design.

```python
app = await conv.evolve("add a coastal walk option to day 2")
print(app.growth_decision.growth_type)   # "extend_current"
print(app.growth_decision.reason)        # "..."
```

This is the behavior that distinguishes SaC from one-shot UI generators.

### Renderer is a viewer, not the SDK

Every `App` has a `code` field — runnable TSX (React 19 + Tailwind +
lucide-react + recharts). How you render it is your choice:

- `sac serve` ships a full local playground
- The bundled iframe renderer (`/renderer/sac-renderer.js`) handles partial
  TSX repair, design-system shimming, and lucide-icon fallbacks
- Hosted: iframe `sac.dynsoft.ai/share/{id}` for a public URL
- Bring your own: Sandpack or any sandbox you control

See [`docs/embedding.md`](./docs/embedding.md) for the trade-offs.

## Customize

Every layer is pluggable via Protocol classes:

```python
from sac import SaC, MemoryStore, FileStore

sac = SaC(
    llm=YourLLMProvider(...),       # any class implementing LLMProvider
    search=YourSearchProvider(...), # any class implementing SearchProvider
    store=FileStore(".sac"),        # or MemoryStore() or your own
)
```

Prompts live in [`src/sac/runtime/prompts/`](./src/sac/runtime/prompts/) and
the default design system is in [`src/sac/renderer/design-systems/default/`](./src/sac/renderer/design-systems/default/).
Both are open-source and community contributions are the highest-leverage
change you can make.

## What SaC is NOT

- **Not a UI library.** No fixed components — the LLM generates structure
  every turn.
- **Not vibe coding.** No developer-in-loop IDE flow; SaC is for end-user
  agents, not developer tools.
- **Not GenUI.** GenUI picks from a component library; SaC generates the
  structure itself. GenUI is the `version == 1` special case.
- **Not a chat replacement.** SaC is a *parallel bandwidth* alongside chat
  (the dual-channel `Φs + Φnl` framing in the [paper](https://arxiv.org/abs/2603.21334)).
  The agent still talks; SaC adds a structured surface to talk *about*.
- **Not chat-only.** Conversation is today's primary input channel, but `App`
  evolves through any signal — natural language, structured affordances,
  environmental events. SaC is the substrate, not the chat box.

## Architecture

```
src/sac/
├── sac.py               # SaC entry point
├── conversation.py      # Conversation primitive (state, history, evolve)
├── types.py             # Pydantic data contracts
├── cli.py               # `sac serve [--transport stdio]`
│
├── runtime/             # Execution engine
│   ├── pipeline/        #   Generate + Evolve orchestration + streaming filter
│   ├── providers/       #   LLM (OpenRouter) + Search (Tavily) + your own
│   ├── prompts/         #   intent / app / growth / classify / search
│   └── store/           #   Memory + File + your own
│
├── server/              # Deployment surfaces
│   ├── http.py          #   FastAPI + SSE for webapp backends
│   └── mcp.py           #   MCP stdio for agent hosts
│
└── renderer/            # Browser-side viewer
    ├── preview.html     #   iframe sandbox
    ├── sac-renderer.js  #   postMessage bridge + partial TSX repair
    └── design-systems/  #   Pluggable component shim + prompt
```

Deeper technical notes: [`docs/architecture.md`](./docs/architecture.md).

## Project status

`v0.1.0` — alpha. The core API (`Conversation`, `App`, `evolve`) is settling
but may shift before `v1.0`. Production readiness for the hosted product is
proven (it's the backend for [sac.dynsoft.ai](https://sac.dynsoft.ai)); the
SDK boundary is what's being polished.

## Contributing

Issues and PRs welcome. The highest-leverage changes right now are **prompt
improvements** in [`src/sac/runtime/prompts/`](./src/sac/runtime/prompts/) and
**real working examples** in [`examples/agents/`](./examples/agents/). For
local dev: `pip install -e '.[server,mcp,dev]'`.

## Security

Found a vulnerability? Email **mulong@mulongxie.me** — please don't open a
public issue. SaC executes LLM-generated code in a sandboxed iframe, so
issues around iframe escape, prompt-injected exfiltration, or sandbox bypass
are especially in scope.

## Citation

If you use SaC in academic work:

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
