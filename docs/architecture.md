# SaC SDK Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Consumer Layer                           │
│                                                                 │
│   Python App          HTTP Client          AI Agent (MCP)       │
│   import sac          fetch /generate      tool: sac.generate   │
│                                                                 │
└────────┬──────────────────┬──────────────────┬──────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SDK Core                                │
│                                                                 │
│  ┌──────────┐    ┌────────────────┐    ┌──────────────────┐     │
│  │   SaC    │───>│  Conversation  │───>│      App         │     │
│  │ (entry)  │    │  (stateful)    │    │  (versioned      │     │
│  │          │    │                │    │   output)        │     │
│  └──────────┘    └────────────────┘    └──────────────────┘     │
│       │                  │                                      │
│       │          ┌───────┴────────┐                             │
│       │          │                │                             │
│       │    generate()        evolve()                           │
│       │          │                │                             │
│       │          ▼                ▼                             │
│  ┌────┴─────────────────────────────────────────────┐          │
│  │                    Runtime                        │          │
│  │                                                   │          │
│  │  ┌──────────┐  ┌───────────┐  ┌───────────────┐  │          │
│  │  │ Pipeline │  │ Providers │  │    Prompts    │  │          │
│  │  │          │  │           │  │               │  │          │
│  │  │ generate │  │ LLM       │  │ app.py        │  │          │
│  │  │ evolve   │  │ Search    │  │ growth.py     │  │          │
│  │  │ stream   │  │           │  │ intent.py     │  │          │
│  │  └──────────┘  └───────────┘  │ search.py     │  │          │
│  │                               └───────────────┘  │          │
│  │  ┌──────────────────────────────────────────┐    │          │
│  │  │                  Store                    │    │          │
│  │  │  MemoryStore (dict + optional file output)│    │          │
│  │  └──────────────────────────────────────────┘    │          │
│  └───────────────────────────────────────────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
         │                  │
         ▼                  ▼
┌──────────────┐    ┌──────────────────────────────────────┐
│    Server    │    │            Renderer                   │
│              │    │                                       │
│  HTTP/SSE    │    │  sac-renderer.js  (parent page API)  │
│  FastAPI     │    │  preview.html     (iframe sandbox)   │
│  /generate   │    │  design-systems/  (pluggable DS)     │
│  /evolve     │    │    default/                          │
│  /stream     │    │      prompt.md   (LLM reference)    │
│  /renderer/* │    │      shim.js     (browser comps)    │
└──────────────┘    └──────────────────────────────────────┘
```

## Core Primitives

```
SaC                          Conversation                    App
┌──────────────────┐         ┌──────────────────┐          ┌──────────────────┐
│ api_key          │         │ id               │          │ code: string     │
│ llm: LLMProvider │────────>│ settings         │────────> │ version: int     │
│ search: Search.. │  create │ model            │  produce │ intent: string   │
│ store: Store     │         │ _apps: list[App] │          │ parent_version   │
├──────────────────┤         ├──────────────────┤          │ search_results   │
│ conversation()   │         │ generate(intent) │          │ suggestions      │
│ generate(intent) │         │ evolve(intent)   │          │ growth_decision  │
│ close()          │         │ stream(intent)   │          │ stages           │
└──────────────────┘         │ current_app      │          └──────────────────┘
                             │ history          │
                             │ version          │
                             └──────────────────┘
```

## Provider Protocols (Pluggable)

```
┌─────────────────────────┐     ┌─────────────────────────┐
│      LLMProvider        │     │     SearchProvider      │
│  (Protocol — any class  │     │  (Protocol — any class  │
│   implementing these    │     │   implementing this     │
│   methods is valid)     │     │   method is valid)      │
├─────────────────────────┤     ├─────────────────────────┤
│ complete(model, msgs)   │     │ search(queries)         │
│   → str                 │     │   → list[SearchResult]  │
│ stream(model, msgs)     │     └─────────────────────────┘
│   → AsyncIterator[str]  │               ▲
└─────────────────────────┘               │
          ▲                               │
          │                               │
┌─────────┴─────────┐          ┌──────────┴──────────┐
│ OpenRouterProvider │          │   TavilyProvider    │
│ (default)          │          │   (default)         │
│ openrouter.ai API  │          │   tavily.com API    │
└────────────────────┘          └─────────────────────┘
```

---

## Generate Pipeline

```
User Intent: "2026 travel guide for Hangzhou"
│
▼
┌─────────────────────────────────────────────────────────┐
│                   Generate Pipeline                      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Step 1: ANALYZE                                  │    │
│  │                                                  │    │
│  │  search_prompt + intent ──> LLM                  │    │
│  │                              │                   │    │
│  │                              ▼                   │    │
│  │                     SearchQuery[]                │    │
│  │                     [                            │    │
│  │                       "Hangzhou travel 2026",    │    │
│  │                       "Hangzhou restaurants",    │    │
│  │                       "Hangzhou attractions"     │    │
│  │                     ]                            │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │                               │
│                         ▼                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Step 2: SEARCH                                   │    │
│  │                                                  │    │
│  │  queries ──> Tavily API (parallel)               │    │
│  │                    │                             │    │
│  │                    ▼                             │    │
│  │             SearchResult[]                       │    │
│  │             [                                    │    │
│  │               { query, answer, sources, images } │    │
│  │               { query, answer, sources, images } │    │
│  │             ]                                    │    │
│  │                    │                             │    │
│  │              ──────┼──> PipelineSearchEvent      │    │
│  │                    │    (sent to frontend)       │    │
│  └────────────────────┬────────────────────────────┘    │
│                       │                                 │
│                       ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Step 3: GENERATE (parallel)                      │    │
│  │                                                  │    │
│  │  ┌──────────────────────┐  ┌──────────────────┐  │    │
│  │  │ Task A: UI Code      │  │ Task B: Suggest  │  │    │
│  │  │                      │  │                  │  │    │
│  │  │ system_prompt        │  │ intent +         │  │    │
│  │  │ + search_results     │  │ search_results   │  │    │
│  │  │ + intent             │  │     │            │  │    │
│  │  │     │                │  │     ▼            │  │    │
│  │  │     ▼                │  │ IntentSugg[]     │  │    │
│  │  │ LLM (streaming)     │  │ [                │  │    │
│  │  │     │                │  │   "Book hotels", │  │    │
│  │  │     ▼                │  │   "Add map",     │  │    │
│  │  │ TSX code tokens     │  │   "Compare..."   │  │    │
│  │  │ (ChunkEvent each)   │  │ ]                │  │    │
│  │  └──────────────────────┘  └──────────────────┘  │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │                               │
│                         ▼                               │
│                   App {                                  │
│                     code: "import React...",             │
│                     version: 1,                         │
│                     intent: "2026 travel guide...",      │
│                     search_results: [...],              │
│                     suggestions: [...]                  │
│                   }                                     │
└─────────────────────────────────────────────────────────┘
```

## Evolve Pipeline

```
New Intent: "add restaurant recommendations"
Current App: v1 (travel guide code)
│
▼
┌─────────────────────────────────────────────────────────┐
│                    Evolve Pipeline                       │
│                                                         │
│  Step 1: SEARCH (same as generate)                      │
│  ──────────────────────────────────                     │
│  Extract queries from new intent → Tavily → results     │
│                                                         │
│  Step 2: UNIFIED GROWTH (single LLM call)               │
│  ────────────────────────────────────────                │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Input to LLM:                                    │    │
│  │                                                  │    │
│  │  system_prompt                                   │    │
│  │  + current_code (full TSX of v1)                 │    │
│  │  + original_intent ("travel guide")              │    │
│  │  + new_intent ("add restaurants")                │    │
│  │  + search_results (restaurant data)              │    │
│  │  + growth_rules                                  │    │
│  │                                                  │    │
│  │ LLM responds with TWO blocks:                    │    │
│  │                                                  │    │
│  │  ```json                                         │    │
│  │  {                                               │    │
│  │    "growthType": "extend_current",               │    │
│  │    "reason": "restaurants complement travel..."  │    │
│  │  }                                               │    │
│  │  ```                                             │    │
│  │                                                  │    │
│  │  ```tsx                                          │    │
│  │  // Complete updated component with restaurants  │    │
│  │  export default function TravelGuide() { ... }   │    │
│  │  ```                                             │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                               │
│                         ▼                               │
│                   App {                                  │
│                     code: "// updated code...",          │
│                     version: 2,                         │
│                     parent_version: 1,                  │
│                     growth_decision: {                  │
│                       growth_type: "extend_current",    │
│                       reason: "..."                     │
│                     }                                   │
│                   }                                     │
└─────────────────────────────────────────────────────────┘
```

## SSE Streaming Flow

```
Browser                    Server                     LLM (OpenRouter)
  │                          │                              │
  │  GET /stream?intent=...  │                              │
  │ ────────────────────────>│                              │
  │                          │                              │
  │  event: stage            │                              │
  │  {analyze: running}      │                              │
  │ <────────────────────────│  extract search queries      │
  │                          │ ────────────────────────────>│
  │                          │ <────────────────────────────│
  │  event: stage            │                              │
  │  {analyze: completed}    │                              │
  │ <────────────────────────│                              │
  │                          │                              │
  │  event: stage            │         Tavily API           │
  │  {search: running}       │              │               │
  │ <────────────────────────│  search ────>│               │
  │                          │  <───────────│               │
  │  event: stage            │                              │
  │  {search: completed}     │                              │
  │ <────────────────────────│                              │
  │                          │                              │
  │  event: search           │                              │
  │  {queries, results}      │  ◄── frontend can show       │
  │ <────────────────────────│      search data NOW         │
  │                          │                              │
  │  event: stage            │                              │
  │  {generate: running}     │                              │
  │ <────────────────────────│  stream code generation      │
  │                          │ ────────────────────────────>│
  │  event: chunk            │                              │
  │  {data: "import..."}     │ <─── token ─────────────────│
  │ <────────────────────────│                              │
  │  event: chunk            │                              │
  │  {data: "React..."}      │ <─── token ─────────────────│
  │ <────────────────────────│                              │
  │  ...                     │  ... (hundreds of chunks)    │
  │                          │                              │
  │  event: stage            │ <─── [DONE] ────────────────│
  │  {generate: completed}   │                              │
  │ <────────────────────────│                              │
  │                          │                              │
  │  event: complete         │                              │
  │  {app: {...}}            │                              │
  │ <────────────────────────│                              │
  │                          │                              │
```

## Renderer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Parent Page                          │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              SaCRenderer (JS)                    │    │
│  │                                                  │    │
│  │  render(code)                                    │    │
│  │    1. _processCode() — strip fences,             │    │
│  │       rewrite @/components/ui/* → __ui_shim__    │    │
│  │    2. _sendToIframe() — postMessage to iframe    │    │
│  │                                                  │    │
│  │  createStream()                                  │    │
│  │    push(token) — accumulate + autoClose +        │    │
│  │                  try transpile (if Babel loaded)  │    │
│  │    end()       — send final code to iframe       │    │
│  │                                                  │    │
│  │  Events: 'render', 'error'                       │    │
│  └──────────────────┬──────────────────────────────┘    │
│                     │ postMessage                        │
│                     ▼                                    │
│  ┌─────────────────────────────────────────────────┐    │
│  │          preview.html (iframe sandbox)           │    │
│  │                                                  │    │
│  │  1. Load Babel standalone (one-time)             │    │
│  │  2. Load React via import map (one-time)         │    │
│  │  3. On message:                                  │    │
│  │     a. Transpile TSX → JS (Babel)                │    │
│  │     b. Fetch & cache shim.js → blob URL          │    │
│  │     c. Replace __ui_shim__ → blob URL            │    │
│  │     d. Create app module blob                    │    │
│  │     e. Dynamic import(appBlob)                   │    │
│  │     f. ReactDOM.render(App) in ErrorBoundary     │    │
│  │  4. Report success/error via postMessage         │    │
│  └──────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │       Design System (pluggable)                  │    │
│  │                                                  │    │
│  │  prompt.md — tells LLM what components exist     │    │
│  │  shim.js   — browser implementations            │    │
│  │             (Button, Card, Dialog, etc.)          │    │
│  │             simplified HTML + Tailwind wrappers   │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Data Flow: Full Request Lifecycle

```
                    User: "today news"
                           │
                           ▼
                   ┌───────────────┐
                   │  index.html   │
                   │  EventSource  │
                   └───────┬───────┘
                           │ GET /stream?intent=today+news
                           ▼
                   ┌───────────────┐
                   │   http.py     │
                   │   FastAPI     │
                   └───────┬───────┘
                           │ conv.stream("today news")
                           ▼
                   ┌───────────────┐
                   │ conversation  │
                   │    .py        │
                   └───────┬───────┘
                           │ stream_generate_pipeline()
                           ▼
              ┌────────────────────────┐
              │    generate.py         │
              │                        │
              │  1. Build system prompt│
              │     app.py             │──── design-system prompt.md
              │     (base + custom     │     (1220 lines of component docs)
              │      + design system)  │
              │                        │
              │  2. Extract queries    │
              │     search.py          │──── LLM call (OpenRouter)
              │                        │
              │  3. Execute search     │
              │     tavily.py          │──── Tavily API (parallel queries)
              │                        │
              │  4. Generate UI code   │
              │     LLM streaming      │──── LLM call (OpenRouter, streaming)
              │                        │
              │  5. Intent suggestions │
              │     intent.py          │──── LLM call (OpenRouter, parallel)
              │                        │
              └────────────┬───────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │  Store        │
                   │  memory.py    │──── save events + optional file output
                   └───────┬───────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   App         │
                   │   {code,      │
                   │    version,   │
                   │    results,   │
                   │    suggest}   │
                   └───────┬───────┘
                           │ SSE events
                           ▼
                   ┌───────────────┐
                   │  index.html   │
                   │  + renderer   │──── preview.html (iframe)
                   │               │     Babel + React + shim.js
                   └───────────────┘
                           │
                           ▼
                    Interactive UI
```

## File Structure

```
src/sac/
│
│  # ─── SDK Core ────────────────────────────
│  __init__.py              Public API exports
│  types.py                 All Pydantic data models
│  sac.py                   SaC class (entry point, DI)
│  conversation.py          Conversation (stateful primitive)
│  cli.py                   CLI (serve, generate)
│
│  # ─── Runtime ─────────────────────────────
│  runtime/
│    pipeline/
│      generate.py          Generate pipeline + streaming
│      evolve.py            Evolve pipeline + streaming
│      events.py            Stage tracking + timing
│    providers/
│      base.py              LLMProvider + SearchProvider protocols
│      openrouter.py        OpenRouter LLM implementation
│      tavily.py            Tavily search implementation
│    prompts/
│      app.py               System prompt builder + model list
│      growth.py            Evolve/growth prompts
│      intent.py            Intent suggestion prompts + parser
│      search.py            Search query extraction prompts
│    store/
│      base.py              ConversationStore protocol
│      memory.py            In-memory store (+ optional file output)
│
│  # ─── Server ──────────────────────────────
│  server/
│    http.py                FastAPI app (REST + SSE + static files)
│    mcp.py                 MCP server (stub)
│    static/
│      index.html           Demo web UI
│
│  # ─── Renderer ────────────────────────────
│  renderer/
│    sac-renderer.js        Parent-page renderer API
│    preview.html           iframe sandbox (Babel + React)
│    design-systems/
│      default/
│        prompt.md          Component docs for LLM
│        shim.js            Browser component implementations
```
