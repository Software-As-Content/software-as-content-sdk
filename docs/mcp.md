# MCP Server

The SaC SDK ships an [MCP (Model Context Protocol)](https://modelcontextprotocol.io)
server so any MCP-aware host — Claude Desktop, Cursor, Cline, custom agent — can
generate and evolve interactive apps as a tool call.

## Install

```bash
pip install sac-sdk[mcp]
```

## Tools exposed

| Tool | Args | Returns |
|------|------|---------|
| `generate_app` | `intent`, `conversation_id?`, `web_search?` | `conversation_id`, `version`, `code` (TSX), `intent`, `suggestions[]`, `search_results[]` |
| `evolve_app` | `conversation_id`, `intent` | `conversation_id`, `version`, `code` (TSX), `growth_decision`, `suggestions[]` |
| `list_conversations` | _(none)_ | `conversations[]` (id, title, event_count, updated_at, model) |
| `get_conversation` | `conversation_id` | id, title, latest_code, latest_intent, history |

The `code` field is runnable TSX (React 19 + Tailwind + lucide-react + recharts).
Hosts that can render TSX (e.g. via artifacts) render directly; others can show
it as text or save to a file.

## Run standalone

```bash
export SAC_API_KEY="sk-or-..."           # OpenRouter key (required)
export SAC_SEARCH_API_KEY="tvly-..."     # Tavily key (optional, enables web search)
export SAC_DATA_DIR=".sac"               # where to persist conversations (optional)

sac serve --transport stdio
```

The server reads JSON-RPC from stdin and writes responses to stdout, per the MCP
stdio transport spec.

## Connect from Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "sac": {
      "command": "sac",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "SAC_API_KEY": "sk-or-...",
        "SAC_SEARCH_API_KEY": "tvly-...",
        "SAC_DATA_DIR": "/Users/you/.sac"
      }
    }
  }
}
```

Restart Claude Desktop. The four tools (`generate_app`, `evolve_app`,
`list_conversations`, `get_conversation`) become available to the assistant.

> **Note:** `command: "sac"` requires `pip install sac-sdk[mcp]` to be on your
> PATH. If you installed with `pipx` or a custom Python, replace with the
> absolute path returned by `which sac`.

## Verify with MCP Inspector

The official [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
gives you a UI to manually call tools without needing a real host:

```bash
npx @modelcontextprotocol/inspector \
  -e SAC_API_KEY="sk-or-..." \
  sac serve --transport stdio
```

Open the URL it prints, switch to the **Tools** tab, and call `generate_app`
with `intent: "3-day Tokyo itinerary"`.

## Conversation state

The MCP host owns the conversation lifecycle:

1. First call: `generate_app(intent="...")` — no `conversation_id` → SaC creates
   a new one and returns its `conversation_id`.
2. Subsequent calls: pass that `conversation_id` to `evolve_app(...)` to chain
   versions. SaC inspects the previous app and decides whether to extend it
   in-place or add a new section.
3. State is persisted to `$SAC_DATA_DIR` (default `./.sac/`) — survives MCP
   server restarts.

## Programmatic verification

```python
import asyncio, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command="sac",
        args=["serve", "--transport", "stdio"],
        env={"PATH": os.environ["PATH"], "SAC_API_KEY": os.environ["SAC_API_KEY"]},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])

            result = await session.call_tool(
                "generate_app",
                {"intent": "3-day Tokyo itinerary"},
            )
            print(result.content[0].text[:200])

asyncio.run(main())
```
