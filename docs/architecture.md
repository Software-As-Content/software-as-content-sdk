# SaC SDK Architecture

> **Status note (2026-05-05):** this document describes the **target architecture** after the dual-channel pivot. Code is partway there — see "Implementation status" at the bottom.

## TL;DR

SaC is a **protocol** for the agent ↔ user interaction layer, with a Python reference implementation. Sister to MCP: where MCP solves "agent → tool" inbound, SaC solves "agent → user → agent" round-trip with **dual-channel** (Φˢ structured affordance + Φⁿˡ natural language) input AND output.

```
                  ┌──────────────────────────────────────────┐
                  │  SaC Pure Interaction Layer (the core)   │
                  │                                          │
                  │  • /inbox + callback                     │
                  │  • Conversation / version chain          │
                  │  • Renderer: Φˢ App + Φⁿˡ chat panel    │
                  │  • Fused LLM call: response → chat OR ui │
                  │  • Frontend essentials (content-grounded)│
                  └──────────────────────────────────────────┘
                                    ↑↓ HTTP
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
         External agents      SaC's bundled        Custom agents
         (OpenClaw, ...)      default agent        (LangGraph, ...)
                              (search, etc.)
         — ALL siblings, all interact via the same protocol —
```

## Two-layer architecture

### Layer 1: SaC pure interaction layer (the protocol)

This is what "SaC the protocol" really means. It owns:

- **`/inbox`** — agents POST `response` here; SaC renders
- **`callback_url`** — SaC POSTs user actions back to the agent that registered it
- **Conversation primitive** — id, version chain, history, callback_url, settings
- **Renderer** — Φˢ channel (interactive React app, iframe-sandboxed) + Φⁿˡ channel (chat panel for assistant text replies)
- **Fused LLM call** — given `response`, decide chat-bubble vs ui-update AND generate the output in one model call (no separate classify step)
- **Frontend essentials** — anything that's *content-grounded* (derivable from given content + intent + prior_app alone): extend_current vs new_page decisions, default intent suggestions, render styling

The interaction layer **does not** know about search, tools, the agent's task graph, the user's intent classification, or any external context. Those are the agent's job.

### Layer 2: agents (sibling level)

Three flavours, all equal:

1. **External agents** — OpenClaw, LangGraph, Claude Agent SDK, Make.com, custom n8n flow, even a bash cron script. Anything that can do HTTP POST.
2. **SaC's bundled default agent** (`sac.builtin_agent`) — ships with SaC for standalone use. Internally does search + LLM (the historical "SaC pipeline"). It calls SaC's /inbox just like any external agent would.
3. **Custom agents written by SDK users** — anyone can write their own agent that talks to /inbox.

All three are **siblings**, not different layers. They cooperate with the SaC core via the same protocol contract.

## The boundary rule

Decide where logic lives by this single test:

| condition | belongs to |
|---|---|
| **Frontend essential** — derivable from (content + intent + prior_app) alone | SaC core |
| **Info essential** — needs to fetch new data, know what tools the agent has, or interpret outside context | agent layer |

Concretely:

| concern | where | notes |
|---|---|---|
| text → React code | SaC core | rendering decision |
| extend_current vs new_page | SaC core | visual decision |
| chat-bubble vs ui-update | SaC core | content shape decision; fused into the same LLM call |
| default intent suggestions | SaC core | content-grounded; agent can override |
| visual styling, layout, spacing | SaC core | rendering |
| search / web lookup | agent | fetches new info |
| analyze / extract search queries | agent | subtask of search |
| classify "is this chat or update" | agent (dissolved) | now expressed as "agent fills `response` and SaC reads its shape" |
| accept user's raw NL message → decide reply | agent | agent's job |
| run background tasks, schedule cron | agent | agent's job |
| know what skills/tools exist | agent | agent's job |

## The protocol

### `POST /inbox` — agent sends content for SaC to render

```json
{
  "conversation_id": "abc" | null,
  "callback_url": "http://...:9000/sac" | null,
  "response": "<agent's plain-text output>",
  "intent": "..." | null,
  "suggestions": [{"label": "...", "intent": "..."}] | null,
  "render_hint": "chat" | "ui" | "auto",
  "context": {...} | null
}
```

Response:

```json
{
  "conversation_id": "abc",
  "url": "http://sac/c/abc",
  "version": 3 | null
}
```

Behavior:
- SaC's fused LLM call inspects `response` and picks one of two output schemas: **chat** (just text → renders to NL panel) or **ui** (React code + growth_decision → new App version)
- `callback_url` if provided is persisted on the conversation; subsequent calls may omit
- `suggestions` if provided override the default ones SaC would generate
- `render_hint` is an escape hatch for agents that need explicit control
- `version` is `null` when SaC chose chat-only (no new App version)

### `POST {callback_url}` — SaC sends user action back to agent

```json
{
  "conversation_id": "abc",
  "intent": "<what the user did or said>",
  "context": {...} | null
}
```

User clicks a button → `intent` is the button label.
User types in chat box → `intent` is the typed text.
Both go through the same callback. Agent receives, processes, and POSTs result back to /inbox.

### Symmetry

```
agent ──response──▶ /inbox       ──renders──▶ user (Φˢ App + Φⁿˡ chat)
                                                    │ click / type
                  callback ◀──intent──── SaC ◀──────┘
agent ◀──── runs follow-up, POSTs new response back ──┘
```

Both directions support both channels. Agent integration cost ≈ 30 lines (post + receive).

## Core primitives

```
SaC                          Conversation                    App
┌──────────────────┐         ┌──────────────────┐          ┌──────────────────┐
│ llm provider     │         │ id               │          │ code: string     │
│ store            │         │ settings         │          │ version: int     │
│ producer (seam)  │────────>│ model            │────────> │ intent: string   │
│                  │  create │ _apps: list[App] │  produce │ parent_version   │
├──────────────────┤         │ callback_url     │          │ growth_decision  │
│ conversation()   │         ├──────────────────┤          │ stages           │
└──────────────────┘         │ generate(...)    │          └──────────────────┘
                             │ evolve(...)      │
                             │ stream(...)      │
                             └──────────────────┘
```

## Pluggable seams

```
LLMProvider          OpenRouterProvider (default)         — used by core LLM call
ConversationStore    MemoryStore | FileStore (default)    — used by core
CodeProducer         DefaultCodeProducer (default)        — pure rendering seam

SearchProvider       TavilyProvider (default)             — used by bundled default agent
                                                            (NOT by SaC core)
```

`CodeProducer` is the only seam strictly required by the protocol layer. All four can be replaced via the `SaC()` constructor or the bundled agent's constructor.

## Renderer (dual-channel UI)

The renderer renders both channels:

- **Φˢ — App version**: iframe sandbox running the latest version's React TSX with Babel + Tailwind + design-system shim. Updates on new versions via SSE (planned step 3).
- **Φⁿˡ — Chat panel**: scrollable panel of assistant text replies (when SaC's LLM call decided "chat"). User can also type into a NL input here, which posts via the callback channel.

The user clicks structured affordances OR types NL. Both feed back to the same agent via `callback_url`.

## File structure

```
src/sac/
├── __init__.py
├── types.py                 pydantic data models
├── sac.py                   SaC class — entry, DI, conversation factory
├── conversation.py          Conversation primitive — version chain + state
├── cli.py                   CLI entrypoints (sac serve)
│
├── runtime/
│   ├── producer.py          CodeProducer Protocol + DefaultCodeProducer (seam)
│   ├── pipeline/
│   │   ├── generate.py      first-version generation
│   │   ├── evolve.py        version-N+1 growth
│   │   └── events.py        stage tracking + timing
│   ├── providers/
│   │   ├── base.py          LLMProvider, SearchProvider protocols
│   │   ├── openrouter.py
│   │   └── tavily.py        (used only by bundled agent)
│   ├── prompts/             prompt builders
│   └── store/               MemoryStore, FileStore
│
├── server/
│   ├── http.py              FastAPI app — /inbox + callback + legacy endpoints
│   ├── mcp.py               MCP server (re-routes to /inbox)
│   └── static/index.html    web preview UI
│
└── renderer/
    ├── sac-renderer.js      parent-page renderer API
    ├── preview.html         iframe sandbox
    └── design-systems/default/   { prompt.md, shim.js }
```

## End-to-end flow (target shape)

### Daily-brief lighthouse (OpenClaw external agent)

```
1. OpenClaw cron fires daily-brief skill
   ├─ Skill collects Gmail / calendar / weather → composes text
   └─ Skill POST /inbox  { response: "<brief text>",
                           callback_url: "http://openclaw.local/sac" }

2. SaC fused LLM call
   ├─ Inspects response shape → decides "ui" (substantive content)
   ├─ Generates React TSX + growth_decision (no prior_app → first version)
   └─ Returns { conversation_id, url, version: 1 }

3. User opens url, sees rendered App in Φˢ channel
   ├─ Clicks "Show last week's trend"
   └─ SaC POST {callback_url}  { conversation_id, intent: "Show last week's trend" }

4. OpenClaw receiver
   ├─ Routes intent to the appropriate skill
   ├─ Skill runs follow-up query → composes new text
   └─ POST /inbox  { conversation_id, response: "<new analysis>" }

5. SaC fused LLM call
   ├─ Has prior_app → evolve path
   ├─ Decides "ui" again, growth_decision = extend_current
   └─ New version v2

6. Browser SSE picks up version change → iframe re-renders to v2
```

### Standalone chat (bundled default agent)

```
1. User types "make me a Hangzhou travel guide" in SaC web chat
2. UI POSTs to bundled-agent endpoint (NOT directly to /inbox)
3. Bundled agent: search Tavily → compose enriched response
4. Bundled agent POST /inbox  { response: "<travel guide data>" }
5. SaC renders to App version, returns url
6. UI navigates browser to url
```

The web chat box has the same shape as any agent — it just happens to live in the same Python process as SaC.

## Implementation status (2026-05-05)

| Component | Status |
|---|---|
| Conversation primitive + version chain | ✅ done |
| Renderer infrastructure (iframe + design system) | ✅ done |
| CodeProducer seam | ✅ done |
| `content` parameter through pipelines (skip search when given) | ✅ done |
| Basic `/inbox` endpoint (single-channel, accepts `content`) | ✅ MVP |
| `callback_url` field on ConversationData | ✅ done |
| `/c/{id}` static viewer + auto-load JS | ✅ done |
| Single `response` field semantics (SaC decides chat vs ui) | ❌ pending |
| Fused LLM call (chat vs ui in one model call) | ❌ pending |
| Default agent extracted to `sac.builtin_agent` | ❌ pending |
| `/generate /send /stream` re-routed through bundled agent | ❌ pending |
| MCP server tools re-routed to /inbox | ❌ pending |
| Callback POST routing for button click + chat input | ❌ pending |
| Renderer SSE for live updates | ❌ pending |
| OpenClaw adapter (bridge service) | ❌ pending |
| End-to-end lighthouse demo | ❌ pending |

## Strategic note

The two-layer architecture (pure interaction layer + sibling agents) is the only shape that scales SaC to a fragmented agent ecosystem cleanly:

- Each new agent system needs ~30 lines of adapter (POST /inbox + receive callback)
- SaC defines the contract; no agent system needs to learn SaC's frontend conventions
- SaC's bundled default agent is just one sibling — it proves dogfood and powers standalone use, but is not privileged

This mirrors MCP's playbook: a clean protocol contract, multiple host implementations, ecosystem grows from interop. The dual-channel design comes directly from the SaC paper — Φˢ + Φⁿˡ are not optional; they're load-bearing.
