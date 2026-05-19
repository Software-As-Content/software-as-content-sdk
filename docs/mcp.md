# MCP Server

The SaC SDK ships an [MCP (Model Context Protocol)](https://modelcontextprotocol.io)
server so any MCP-aware host — Claude Code, Claude Desktop, Cursor, Cline, custom
agent — can generate, evolve, and **interact** with live apps through tool calls.

## Install

```bash
pip install sac-sdk
```

## Tools exposed

| Tool | Args | Returns |
|------|------|---------|
| `generate_app` | `intent`, `conversation_id?` | `conversation_id`, `version`, `url`, `type` |
| `evolve_app` | `conversation_id`, `intent` | `conversation_id`, `version`, `url`, `type` |
| `wait_for_action` | `conversation_id`, `timeout?` | `action` (intent + context) or `timed_out: true` |
| `list_conversations` | _(none)_ | `conversations[]` |
| `get_conversation` | `conversation_id` | conversation state + `url` |

## Interactive loop

The key difference from a one-shot GenUI tool: SaC supports a **bidirectional
interaction loop** via `wait_for_action`. The MCP host generates an app, waits
for user interaction, and evolves the app based on what the user clicked.

```
1. generate_app("travel planner for Tokyo")
   → { conversation_id: "abc", url: "http://127.0.0.1:8000/c/abc", version: 1 }

2. Show url to user — they open it in a browser and see the live app

3. wait_for_action("abc")
   → blocks until user clicks a button, e.g. "Add budget breakdown"
   → { action: { intent: "Add budget breakdown", context: {...} } }

4. evolve_app("abc", "Add budget breakdown with daily costs")
   → { version: 2, url: "..." }
   (user's browser updates in real-time via SSE streaming)

5. wait_for_action("abc")  — repeat
```

This loop runs entirely through MCP tool calls — no callbacks, no subprocesses,
no thread management. Claude Code (or any MCP host) naturally handles the
blocking `wait_for_action` as a tool call that takes time to return.

## Architecture

When launched via `sac serve --transport stdio`, the MCP server:

1. Starts an **HTTP server in the background** (default port 8000) for the
   viewer UI and API endpoints
2. Serves **MCP tools over stdio** for the host (Claude Code, etc.)
3. Routes `generate_app`/`evolve_app` through the HTTP server's `/inbox`
   endpoint, so the viewer sees streaming updates in real-time
4. `wait_for_action` reads from an in-process action queue — when a user
   clicks a button in the viewer, the action is queued and returned to the
   MCP tool call

If a healthy SaC HTTP server is already running on the configured port (e.g.
from a prior `sac serve`), the MCP server **reuses it** instead of starting a
new one. This means Codex and Claude Code can coexist on the same SaC instance.

## Run standalone

```bash
export SAC_API_KEY="sk-or-..."           # OpenRouter key (required)
export SAC_SEARCH_API_KEY="tvly-..."     # Tavily key (optional, enables web search)
export SAC_DATA_DIR=".sac"               # where to persist conversations (optional)
export SAC_PORT="8000"                   # HTTP server port (optional)

sac serve --transport stdio
```

## Connect from Claude Code

Add to your project's `.mcp.json` or global MCP config:

```json
{
  "mcpServers": {
    "sac": {
      "command": "sac",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "SAC_API_KEY": "sk-or-...",
        "SAC_SEARCH_API_KEY": "tvly-...",
        "SAC_DATA_DIR": "/path/to/.sac"
      }
    }
  }
}
```

Claude Code will have access to `generate_app`, `evolve_app`, `wait_for_action`,
`list_conversations`, and `get_conversation`.

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

> **Note:** `command: "sac"` requires `pip install sac-sdk` to be on your
> PATH. If you installed with `pipx` or a custom Python, replace with the
> absolute path returned by `which sac`.

## Verify with MCP Inspector

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
   a new one and returns its `conversation_id` + viewer `url`.
2. Subsequent calls: pass that `conversation_id` to `evolve_app(...)` to chain
   versions. SaC inspects the previous app and decides whether to extend it
   in-place or add a new section.
3. Between evolve calls: `wait_for_action(conversation_id)` blocks until the
   user interacts with the live app. Times out after 5 minutes by default.
4. State is persisted to `$SAC_DATA_DIR` (default `./.sac/`) — survives MCP
   server restarts.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SAC_API_KEY` | Yes | — | OpenRouter API key |
| `SAC_SEARCH_API_KEY` | No | — | Tavily API key (enables web search in generate) |
| `SAC_DATA_DIR` | No | `.sac` | Directory for conversation persistence |
| `SAC_MODEL` | No | (built-in default) | Default LLM model ID |
| `SAC_PORT` | No | `8000` | HTTP server port for the viewer |
