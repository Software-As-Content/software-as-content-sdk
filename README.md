# SaC SDK

**Software as Content** — an open-source Python SDK that gives any AI agent the ability to generate and evolve interactive UI through conversation.

SaC is the superset of GenUI. GenUI is just `conversation.version == 1`.

## Quickstart

```python
from sac import SaC

sac = SaC(api_key="sk-...")
app = await sac.generate("2026 travel guide for Hangzhou")
print(app.code)  # runnable TSX
```

## Multi-turn Evolution

```python
conv = sac.conversation()
app = await conv.generate("travel guide for Hangzhou", web_search=True)
app = await conv.evolve("add restaurant recommendations")
app = await conv.evolve("make it an interactive map")

print(conv.version)  # 3
print(conv.history)  # [v1, v2, v3]
```

## Streaming

```python
async for event in conv.stream("travel guide"):
    if event.type == "stage":       # analyze / search / generate
        print(f"Stage: {event.name} → {event.status}")
    elif event.type == "chunk":     # code fragment
        print(event.data, end="")
    elif event.type == "complete":  # final result
        render(event.app)
```

## Custom Providers

```python
sac = SaC(
    llm=AnthropicProvider(api_key="..."),
    search=TavilyProvider(api_key="..."),
    store=SQLiteStore("./sac.db"),
)
```

## Run as Server

```bash
# HTTP/SSE server (for browser frontends)
sac serve --port 3000

# MCP server (for AI agents)
sac serve --transport stdio
```

## Architecture

```
src/sac/
├── client.py          # SaC entry point
├── conversation.py    # Core primitive: stateful conversation
├── types.py           # Pydantic models (data contracts)
├── pipeline/          # Generate + Evolve orchestration
├── providers/         # Pluggable LLM + Search backends
├── prompts/           # Prompt templates + strategies
├── store/             # Conversation persistence
└── server/            # HTTP/SSE + MCP deployment
```

**Core primitives:** `SaC → Conversation → App`

## What is Software as Content?

Software as Content (SaC) proposes that software is no longer a static artifact that gets "developed" — it's the natural output of conversation. UI becomes content, generated and consumed like articles or answers, evolving with each interaction.

- **Paper:** [arxiv link]
- **Product:** [product link]

## License

MIT
