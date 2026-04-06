# SaC SDK Implementation Plan

## Context

Software as Content (SaC) is a new paradigm where AI agents generate and evolve interactive UI through conversation. The current product (`software-as-content-website`) has a working TypeScript implementation with tightly coupled frontend and backend.

**Goal:** Create a standalone Python SDK (`sac-sdk`) that extracts the backend logic into a reusable, open-source package. The current product will become a pure frontend consumer of this SDK.

**Why now:** Product is already published (arxiv'd). The SDK enables any AI company/developer to add SaC capability to their agent systems. SaC = GenUI superset (GenUI is just `conversation.version == 1`).

---

## SDK Architecture

```
sac-sdk/
├── pyproject.toml                    # Package config, dependencies
├── README.md                         # 30-second quickstart
├── examples/
│   ├── quickstart.py                 # 3-line generate
│   ├── conversation.py               # Multi-turn evolve
│   ├── streaming.py                  # SSE streaming
│   └── custom_provider.py            # Bring your own LLM
│
├── src/sac/
│   ├── __init__.py                   # Public API: SaC, Conversation, App
│   ├── client.py                     # SaC entry point
│   ├── conversation.py               # Stateful conversation (core primitive)
│   ├── types.py                      # Pydantic models (data contracts)
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── generate.py               # Generation pipeline (analyze → search → generate)
│   │   ├── evolve.py                 # Evolution pipeline (growth decision + code gen)
│   │   └── events.py                 # StageEvent, ChunkEvent, CompleteEvent
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                   # LLMProvider / SearchProvider protocols
│   │   ├── openrouter.py             # Default LLM provider (OpenRouter)
│   │   └── tavily.py                 # Default search provider (Tavily)
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── app.py                    # Base generation prompts
│   │   ├── growth.py                 # Evolution/growth prompts
│   │   ├── intent.py                 # Intent suggestion prompts
│   │   ├── search.py                 # Search query extraction prompts
│   │   ├── judge.py                  # Quality evaluation prompts
│   │   └── templates/
│   │       └── design-system.md      # Default design system reference
│   │
│   ├── store/
│   │   ├── __init__.py
│   │   ├── base.py                   # ConversationStore protocol
│   │   └── memory.py                 # In-memory store (default)
│   │
│   └── server/
│       ├── __init__.py
│       ├── http.py                   # FastAPI/SSE server
│       └── mcp.py                    # MCP server (future, stub for now)
│
└── tests/
    ├── test_types.py
    ├── test_pipeline.py
    ├── test_conversation.py
    ├── test_providers.py
    └── test_prompts.py
```

---

## Implementation Steps

### Step 1: Project Setup
- `pyproject.toml` with dependencies: `pydantic`, `httpx`, `fastapi`, `uvicorn`, `sse-starlette`
- Python 3.11+ target
- `src/sac/` package structure
- Basic README with quickstart example

### Step 2: Types (`src/sac/types.py`)
Rewrite all TypeScript types as Pydantic models:
- `App` — the core output (code, version, intent, parent_version, search_results, suggestions, metadata)
- `Conversation` — conversation metadata (id, title, settings, latest_code, latest_intent)
- `ConversationSettings` — (custom_instructions, use_design_system, enable_web_search, intent_rules, growth_rules)
- `ConversationEvent` — discriminated union (MessageEvent, GenerationEvent, GrowthEvent, ErrorEvent)
- `StageSnapshot` — (name, status, duration)
- `SearchQuery`, `SearchResult`, `IntentSuggestion`
- `GrowthDecision` — (growth_type: extend_current | new_page, reason)
- `JudgeEvalResult` — full L0-L5 evaluation structure
- Request/response models for pipeline operations

**Source reference:** `src/types/conversation.ts` + `src/types/index.ts`

### Step 3: Provider Protocols (`src/sac/providers/`)
Define abstract interfaces:

```python
class LLMProvider(Protocol):
    async def complete(self, model: str, messages: list[Message], **kwargs) -> str: ...
    async def stream(self, model: str, messages: list[Message], **kwargs) -> AsyncIterator[str]: ...

class SearchProvider(Protocol):
    async def search(self, queries: list[str], **kwargs) -> list[SearchResult]: ...
```

Implement:
- `OpenRouterProvider` — HTTP calls to `https://openrouter.ai/api/v1/chat/completions` with Bearer auth
- `TavilyProvider` — HTTP calls to `https://api.tavily.com/search`, parallel query execution

**Source reference:** `callLLM()` in `generate-agentic/route.ts`, `tavily.ts`

### Step 4: Prompts (`src/sac/prompts/`)
Port all prompt templates from TypeScript:
- `app.py` — `BASE_SYSTEM_PROMPT`, `build_final_system_prompt()`, `build_generation_prompt()`
- `growth.py` — `DEFAULT_GROWTH_RULES`, `build_growth_prompt()`
- `intent.py` — `DEFAULT_INTENT_RULES`, `get_intent_suggestion_prompt()`, `parse_intent_suggestions()`
- `search.py` — `get_search_query_extraction_prompt()`, `build_search_context_prompt()`, `should_enable_search()`
- `judge.py` — `JUDGE_SYSTEM_PROMPT`, `UI_VERIFIER_SYSTEM_PROMPT`, `build_evaluation_prompt()`, parser functions
- Copy `design-system.md` to `prompts/templates/`

**Source reference:** All files in `src/lib/*-prompts.ts`, `src/lib/design-system.md`

### Step 5: Store (`src/sac/store/`)
Port conversation persistence:
- `ConversationStore` protocol with methods: `list_conversations`, `get_conversation`, `create_conversation`, `update_conversation`, `delete_conversation`, `get_events`, `add_event`
- `MemoryStore` — in-memory dict-based implementation (default)
- Event appending auto-updates conversation metadata (latest_code, latest_intent, event_count)

**Source reference:** `src/lib/conversation-store.ts`

### Step 6: Pipeline (`src/sac/pipeline/`)
Port the two core pipelines:

**Generate pipeline** (`generate.py`):
1. If web_search enabled: extract_search_queries → execute_searches → generate_ui_with_data
2. If web_search disabled: direct generation
3. Parallel: generate intent suggestions alongside UI generation
4. Stage tracking throughout (analyze → search → generate)
5. Returns `App` object

**Evolve pipeline** (`evolve.py`):
1. Extract search queries from new intent
2. Execute searches
3. Build unified growth prompt (decision + code in single LLM call)
4. Parse growth response (JSON decision block + TSX code block)
5. Parallel intent suggestion generation
6. Returns evolved `App` object

**Events** (`events.py`):
- `StageEvent` — pipeline stage changes
- `ChunkEvent` — streaming code chunks
- `CompleteEvent` — final App result
- `ErrorEvent` — pipeline errors

**Source reference:** `src/app/api/generate-agentic/route.ts`, `src/app/api/grow-app/route.ts`

### Step 7: Conversation (`src/sac/conversation.py`)
The core stateful primitive:

```python
class Conversation:
    def __init__(self, id, pipeline, store, settings)

    async def generate(self, intent, **opts) -> App
    async def evolve(self, intent, **opts) -> App
    async def stream(self, intent, **opts) -> AsyncIterator[Event]

    @property
    def current_app(self) -> App | None
    @property
    def history(self) -> list[App]
    @property
    def version(self) -> int
```

- Wraps pipeline calls with state management
- Auto-persists events to store
- Tracks current_app, version, intent history
- `generate()` for first-time or fresh generation
- `evolve()` for incremental growth (uses current_app as context)
- `stream()` yields StageEvent/ChunkEvent/CompleteEvent

### Step 8: Client (`src/sac/client.py`)
Entry point that wires everything together:

```python
class SaC:
    def __init__(self, api_key, search_api_key=None, llm=None, search=None, store=None, prompts=None)

    def conversation(self, id=None) -> Conversation
    async def generate(self, intent, **opts) -> App  # shortcut: creates temp conversation
```

- Creates providers from api_key if not explicitly provided
- Creates default MemoryStore if not provided
- `conversation()` creates or loads a Conversation instance
- `generate()` is a convenience shortcut for one-off generation

### Step 9: HTTP Server (`src/sac/server/http.py`)
FastAPI app that exposes SDK as HTTP/SSE service:

- `POST /generate` — generate app from intent
- `POST /evolve` — evolve existing conversation
- `GET /conversations` — list conversations
- `GET /conversations/{id}` — get conversation with history
- `GET /stream` — SSE endpoint for streaming generation
- CLI entry: `python -m sac.server.http` or `sac serve --port 3000`

### Step 10: Public API (`src/sac/__init__.py`)
Clean exports:

```python
from sac.client import SaC
from sac.conversation import Conversation
from sac.types import App, ConversationSettings, SearchResult, IntentSuggestion
from sac.providers.base import LLMProvider, SearchProvider
from sac.store.base import ConversationStore
```

### Step 11: Examples + CLI
- `examples/quickstart.py` — 3 lines to generate first app
- `examples/conversation.py` — multi-turn evolve
- `examples/streaming.py` — SSE streaming with stage events
- `examples/custom_provider.py` — bring your own LLM
- CLI via `pyproject.toml [project.scripts]`: `sac = "sac.cli:main"`

---

## Key Design Decisions

1. **Pydantic for types** — validation, serialization, IDE support out of box
2. **httpx for HTTP** — async-first, supports streaming
3. **Protocol classes for providers** — structural typing, no inheritance needed
4. **AsyncIterator for streaming** — native Python async, maps to SSE naturally
5. **MemoryStore as default** — zero setup, SQLite as optional extra later
6. **MCP server as stub** — structure in place, implementation after core is solid

---

## Files to reference from existing codebase

| SDK module | Reference TS file |
|---|---|
| `types.py` | `src/types/conversation.ts` + `src/types/index.ts` |
| `providers/openrouter.py` | `callLLM()` in `src/app/api/generate-agentic/route.ts` |
| `providers/tavily.py` | `src/lib/tavily.ts` |
| `prompts/app.py` | `src/lib/app-prompts.ts` |
| `prompts/growth.py` | `src/lib/growth-prompts.ts` |
| `prompts/intent.py` | `src/lib/intent-prompts.ts` |
| `prompts/search.py` | `src/lib/search-prompts.ts` |
| `prompts/judge.py` | `src/lib/judge-prompts.ts` |
| `store/memory.py` | `src/lib/conversation-store.ts` |
| `pipeline/generate.py` | `src/app/api/generate-agentic/route.ts` |
| `pipeline/evolve.py` | `src/app/api/grow-app/route.ts` |
| `prompts/templates/design-system.md` | `src/lib/design-system.md` |

---

## Verification Plan

1. **Unit tests**: Types serialize/deserialize correctly, prompt builders produce expected output, parsers handle edge cases
2. **Integration test**: `SaC(api_key=...).generate("hello world")` produces valid TSX code
3. **Conversation test**: `conv.generate()` then `conv.evolve()` produces coherent evolution with version tracking
4. **Server test**: Start HTTP server, call `/generate` via curl, verify SSE streaming works
5. **Parity test**: Compare SDK output with current TS product output for same inputs — should be functionally equivalent
