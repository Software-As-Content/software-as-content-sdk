# SaC SDK Architecture

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
| chat-bubble vs ui-update | agent decides via `type` field; SaC has fallback classifier |
| default intent suggestions | SaC core | content-grounded; agent can override |
| visual styling, layout, spacing | SaC core | rendering |
| search / web lookup | agent | fetches new info |
| analyze / extract search queries | agent | subtask of search |
| classify "is this chat or update" | agent sets `type: "ui"` or `type: "chat"` explicitly |
| accept user's raw NL message → decide reply | agent | agent's job |
| run background tasks, schedule cron | agent | agent's job |
| know what skills/tools exist | agent | agent's job |

## The protocol

### `POST /inbox` — agent sends content for SaC to render

```json
{
  "conversation_id": "abc" | null,
  "callback_url": "codex://..." | "ws://..." | "http://..." | null,
  "callback_format": "codex_exec_resume" | "openclaw_gateway" | null,
  "content": "<agent's content — markdown, plain text, or structured>",
  "intent": "..." | null,
  "user_message": "..." | null,
  "type": "ui" | "chat" | null
}
```

Response:

```json
{
  "conversation_id": "abc",
  "url": "http://127.0.0.1:18420/c/abc",
  "version": 3 | null,
  "type": "ui" | "chat"
}
```

Behavior:
- `type: "ui"` → render `content` as a new App version
- `type: "chat"` → store `content` as an assistant chat bubble (no new version)
- `type` omitted → SaC decides: agent-owned conversations (has `callback_url`) default to UI; otherwise the legacy classifier picks
- `callback_url` is persisted on the conversation; subsequent calls may omit
- `user_message` lets the agent display the user's original verbatim input in the viewer (separate from agent-expanded `intent`)
- `version` is `null` when `type: "chat"`

### `POST /c/{id}/action` — user action enters SaC

The viewer calls this when the user clicks a button or types a message:

```json
{
  "intent": "<button label or typed text>",
  "context": {...} | null
}
```

SaC then either:
- **Callback mode** (conversation has `callback_url`) → dispatches to the registered agent (HTTP POST, WebSocket RPC, or `codex exec resume`)
- **Pull mode** (no `callback_url`) → queues the action; the agent picks it up via `GET /c/{id}/wait-action` (long-poll)

Either way, the agent eventually POSTs back to `/inbox` to evolve the app or reply via chat.

### Symmetry

```
agent ──content──▶ /inbox        ──renders──▶ user (Φˢ App + Φⁿˡ chat)
                                                    │ click / type
              callback ◀──intent──── /action ◀──────┘
                        OR pull (wait-action)
agent ◀──── runs follow-up, POSTs new content back ──┘
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
LLMProvider          OpenRouterProvider (default)         — any OpenAI-compatible endpoint
                     AnthropicProvider                    — Anthropic Messages API
ConversationStore    MemoryStore | FileStore (default)    — used by core
CodeProducer         DefaultCodeProducer (default)        — pure rendering seam

SearchProvider       TavilyProvider (default)             — used by bundled default agent
                                                            (NOT by SaC core)
```

Provider is auto-detected: `sk-ant-*` keys → Anthropic, otherwise OpenRouter. Override with `SAC_API_BASE` for any OpenAI-compatible endpoint (OpenAI, ollama, vLLM, etc.).

`CodeProducer` is the only seam strictly required by the protocol layer. All four can be replaced via the `SaC()` constructor or the bundled agent's constructor.

## Renderer (dual-channel UI)

The renderer renders both channels:

- **Φˢ — App version**: iframe sandbox running the latest version's React TSX with Babel + Tailwind + design-system shim. Updates on new versions via SSE.
- **Φⁿˡ — Chat panel**: scrollable panel of assistant text replies (when SaC's LLM call decided "chat"). User can also type into a NL input here, which posts via the callback channel.

The user clicks structured affordances OR types NL. Both feed back to the same agent via `callback_url`.

## File structure

```
src/sac/
├── __init__.py
├── types.py                 pydantic data models
├── sac.py                   SaC class — entry, DI, conversation factory
├── conversation.py          Conversation primitive — version chain + state
├── cli.py                   CLI entrypoints (sac serve, sac setup, sac publish)
│
├── agent/
│   ├── agent.py             StandaloneAgent (bundled default agent)
│   └── legacy.py            LegacyShim for /send + /classify endpoints
│
├── runtime/
│   ├── producer.py          CodeProducer Protocol + DefaultCodeProducer (seam)
│   ├── pipeline/
│   │   ├── generate.py      first-version generation
│   │   ├── evolve.py        version-N+1 growth
│   │   └── events.py        stage tracking + timing
│   ├── providers/
│   │   ├── base.py          LLMProvider, SearchProvider protocols
│   │   ├── openrouter.py    OpenAI-compatible (OpenRouter, OpenAI, ollama, etc.)
│   │   ├── anthropic.py     Anthropic Messages API
│   │   └── tavily.py        search (used only by bundled agent)
│   ├── prompts/             prompt builders + model definitions
│   └── store/               MemoryStore, FileStore
│
├── server/
│   ├── http/
│   │   ├── http.py          FastAPI app — /inbox + callback + viewer
│   │   ├── callbacks/       callback adapters (OpenClaw, Codex, HTTP)
│   │   └── static/          viewer UI (HTML + CSS + JS)
│   └── mcp/
│       └── mcp.py           MCP server (re-routes to /inbox, embeds HTTP)
│
└── renderer/
    ├── sac-renderer.js      parent-page renderer API
    ├── preview.html         iframe sandbox
    └── design-systems/default/   { prompt.md, shim.js }
```

## End-to-end flow (target shape)

### Callback mode (OpenClaw / Codex external agent)

```
1. Agent composes content and POSTs /inbox
   { content: "<brief>", type: "ui",
     callback_url: "ws://...",  callback_format: "openclaw_gateway" }

2. SaC renders v1 → returns { conversation_id, url, version: 1 }

3. User opens url, sees rendered App in Φˢ channel
   ├─ Clicks "Show last week's trend"
   └─ Viewer POST /c/{id}/action  { intent: "Show last week's trend" }

4. SaC dispatches via callback_url (WebSocket RPC, or `codex exec resume`)
   └─ Agent receives the action

5. Agent runs follow-up → POST /inbox
   { conversation_id, content: "<new analysis>", type: "ui" }
   — or, for a conversational reply —
   { conversation_id, content: "<reply text>", type: "chat" }

6. SaC renders v2 (ui) or shows chat bubble (chat) → browser updates via SSE
```

### Pull mode (MCP-based agent: Claude Code)

```
1. Claude Code calls `generate_app(intent)` MCP tool
   └─ Tool POSTs /inbox internally, returns viewer URL

2. Claude Code calls `wait_for_action(conversation_id)` — blocks

3. User opens viewer, clicks a button or types
   └─ Viewer POST /c/{id}/action queues the action

4. `wait_for_action` returns the action to Claude Code with recent context

5. Claude Code calls either:
   ├─ `evolve_app(id, intent)` → new ui version
   └─ `send_chat(id, message)` → chat bubble, no version

6. Back to step 2 (loop)
```

No callback URL needed — the MCP tool call itself is the "callback".

## Implementation status

| Component | Status |
|---|---|
| Conversation primitive + version chain | ✅ |
| Renderer infrastructure (iframe + design system) | ✅ |
| Progressive evolve (S/R diff + change highlighting) | ✅ |
| `/inbox` endpoint (`type: ui` / `chat`, content + callback) | ✅ |
| `/c/{id}/action` callback dispatch + pull queue | ✅ |
| `/c/{id}/wait-action` long-poll endpoint | ✅ |
| `/c/{id}/events` SSE viewer updates | ✅ |
| Default agent (StandaloneAgent) | ✅ |
| MCP server (stdio transport, embedded HTTP) | ✅ |
| MCP tools: generate_app / evolve_app / wait_for_action / send_chat | ✅ |
| OpenClaw adapter (gateway WebSocket callback) | ✅ |
| Codex adapter (`codex_exec_resume` subprocess) | ✅ |
| Multi-provider support (OpenRouter, Anthropic, OpenAI-compat) | ✅ |
| `sac setup claude-code` CLI installer | ✅ |
| `sac publish` CLI for external agents | ✅ |
| Fused LLM call (chat vs ui in one model call) | pending |

## Strategic note

The two-layer architecture (pure interaction layer + sibling agents) is the only shape that scales SaC to a fragmented agent ecosystem cleanly:

- Each new agent system needs ~30 lines of adapter (POST /inbox + receive callback)
- SaC defines the contract; no agent system needs to learn SaC's frontend conventions
- SaC's bundled default agent is just one sibling — it proves dogfood and powers standalone use, but is not privileged

This mirrors MCP's playbook: a clean protocol contract, multiple host implementations, ecosystem grows from interop. The dual-channel design comes directly from the SaC paper — Φˢ + Φⁿˡ are not optional; they're load-bearing.
