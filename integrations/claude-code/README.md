# SaC + Claude Code Integration

SaC connects to Claude Code via MCP (Model Context Protocol). Claude Code gets
tools to generate, evolve, and interact with live apps — all through standard
MCP tool calls.

## Setup

```bash
pip install sac-sdk
sac setup claude-code
```

The setup wizard will:
1. Ask you to choose an LLM provider (OpenRouter, Anthropic, OpenAI, or custom)
2. Collect your API key and optional settings
3. Register the SaC MCP server with Claude Code

Restart Claude Code after setup to activate.

### Remove

```bash
sac setup claude-code --remove
```

## Verify

```bash
claude mcp list
```

You should see `sac` listed and connected. Then in Claude Code, try:

```
Create an interactive dashboard showing my project structure using SaC.
```

Claude Code will call `generate_app`, show you the viewer URL, then enter
the interaction loop via `wait_for_action`.

## How It Works

Once connected, Claude Code has access to these tools:

| Tool | Description |
|------|-------------|
| `generate_app` | Create a new interactive app from an intent |
| `evolve_app` | Update an existing app based on user action |
| `wait_for_action` | Block until the user interacts with the app |
| `send_chat` | Send a chat reply without changing the app |
| `list_conversations` | List all conversations |
| `get_conversation` | Get conversation state and viewer URL |

The typical interaction loop:

```
1. generate_app("travel planner for Tokyo")
   -> { conversation_id: "abc", url: "http://127.0.0.1:18420/c/abc" }

2. User opens the URL and sees the live app

3. wait_for_action("abc")
   -> blocks until user clicks a button, e.g. "Add budget breakdown"

4. evolve_app("abc", "Add budget breakdown with daily costs")
   -> user's browser updates in real-time via SSE streaming

5. wait_for_action("abc") -- repeat
```

This loop runs entirely through MCP tool calls. Claude Code handles the
blocking `wait_for_action` naturally as a tool call that takes time to return.
