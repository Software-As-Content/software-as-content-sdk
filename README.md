# SaC SDK

**Software as Content** — an open-source Python SDK that gives any AI agent the ability to generate and evolve interactive UI through conversation.

SaC is the superset of GenUI. GenUI is just `conversation.version == 1`.

## Setup

### Prerequisites

- Python 3.11+
- An [OpenRouter](https://openrouter.ai/) API key (for LLM access)
- (Optional) A [Tavily](https://tavily.com/) API key (for web search)

### Install

```bash
git clone <repo-url>
cd software-as-content-sdk
pip install -e ".[server]"
```

### Configure API Keys

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Then edit `.env` and fill in your keys:

```
# Required — OpenRouter API key (get one at https://openrouter.ai/keys)
SAC_API_KEY=sk-or-v1-your-key-here

# Optional — Tavily API key for web search (get one at https://app.tavily.com/)
# Without this, generation still works but won't include real-time data
SAC_SEARCH_API_KEY=tvly-your-key-here
```

### Run

```bash
# Start the HTTP server with browser preview
python -m sac.cli serve

# Open http://localhost:3000 in your browser
```

## Usage

### Python Library

```python
from sac import SaC

sac = SaC(api_key="sk-...")
app = await sac.generate("2026 travel guide for Hangzhou")
print(app.code)  # runnable TSX
```

### Multi-turn Evolution

```python
conv = sac.conversation()
app = await conv.generate("travel guide for Hangzhou", web_search=True)
app = await conv.evolve("add restaurant recommendations")
app = await conv.evolve("make it an interactive map")

print(conv.version)  # 3
print(conv.history)  # [v1, v2, v3]
```

### Streaming

```python
async for event in conv.stream("travel guide"):
    if event.type == "stage":       # analyze / search / generate
        print(f"Stage: {event.name} -> {event.status}")
    elif event.type == "chunk":     # code fragment
        print(event.data, end="")
    elif event.type == "complete":  # final result
        render(event.app)
```

### Custom Providers

```python
sac = SaC(
    llm=AnthropicProvider(api_key="..."),
    search=TavilyProvider(api_key="..."),
    store=MemoryStore(output_dir="output"),
)
```

### HTTP Server

```bash
# Start with default settings
python -m sac.cli serve

# Custom port
python -m sac.cli serve --port 8080
```

## Architecture

```
src/sac/
├── sac.py               # SaC entry point
├── conversation.py      # Core primitive: stateful conversation
├── types.py             # Pydantic models (data contracts)
├── cli.py               # CLI (sac serve, sac generate)
│
├── runtime/             # Execution engine
│   ├── pipeline/        #   Generate + Evolve orchestration
│   ├── providers/       #   Pluggable LLM + Search backends
│   ├── prompts/         #   Prompt templates
│   └── store/           #   Conversation persistence
│
├── server/              # HTTP/SSE deployment
│   └── http.py
│
└── renderer/            # Browser preview (independent module)
    ├── sac-renderer.js  #   Renderer API
    ├── preview.html     #   iframe sandbox
    └── design-systems/  #   Pluggable design system
        └── default/
            ├── prompt.md    # LLM component reference
            └── shim.js      # Browser component implementations
```

**Core primitives:** `SaC -> Conversation -> App`

## What is Software as Content?

Software as Content (SaC) proposes that software is no longer a static artifact that gets "developed" — it's the natural output of conversation. UI becomes content, generated and consumed like articles or answers, evolving with each interaction.

- **Paper:** [arxiv link]
- **Product:** [product link]

## License

MIT
