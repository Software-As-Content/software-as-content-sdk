"""
MCP Server — exposes the SaC SDK as Model Context Protocol tools.

Launch via:
    sac serve --transport stdio

This starts both:
  - An MCP server over stdio (for Claude Code / MCP hosts)
  - An HTTP server in the background (for the viewer UI)

Tools exposed:
    generate_app(intent, conversation_id?, web_search?)
        → first version of an app. Returns conversation_id + viewer URL.

    evolve_app(conversation_id, intent)
        → next version of an app, evolved from the current state.

    wait_for_action(conversation_id, timeout?)
        → blocks until a user clicks a button/submits in the viewer app.
          Returns the action intent + context. This is how the MCP host
          receives interactive feedback without needing callbacks.

    list_conversations()
        → all conversations persisted by this SaC instance.

    get_conversation(conversation_id)
        → full state of one conversation (latest code + history).

The generate → wait_for_action → evolve loop:
  1. Agent calls generate_app("travel planner") → gets URL + code
  2. User opens URL, interacts with the app, clicks "Add budget breakdown"
  3. Agent calls wait_for_action(conv_id) → blocks → returns {intent: "Add budget breakdown"}
  4. Agent composes new content, calls evolve_app(conv_id, "Add budget breakdown")
  5. Repeat from step 2

Required env:
  - SAC_API_KEY            OpenRouter API key
  - SAC_SEARCH_API_KEY     (optional) Tavily key — enables web search
  - SAC_DATA_DIR           (optional) where to persist conversations (default: .sac)
  - SAC_MODEL              (optional) default model id
  - SAC_PORT               (optional) HTTP server port (default: 8000)
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "MCP server dependencies not installed. Run: pip install sac-sdk[mcp]"
    ) from e

from sac.runtime.prompts.app import DEFAULT_MODEL
from sac.runtime.store.file import FileStore
from sac.sac import SaC

logger = logging.getLogger(__name__)


# ─── Process-wide state ──────────────────────────────────────────


_SAC: SaC | None = None
_HTTP_BASE_URL: str | None = None
_HTTP_APP: Any = None  # FastAPI app reference (for action_queue access)


def _get_sac() -> SaC:
    global _SAC
    if _SAC is None:
        api_key = os.environ.get("SAC_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "SAC_API_KEY environment variable is required for the MCP server."
            )
        _SAC = SaC(
            api_key=api_key,
            search_api_key=os.environ.get("SAC_SEARCH_API_KEY"),
            model=os.environ.get("SAC_MODEL", DEFAULT_MODEL),
            store=FileStore(os.environ.get("SAC_DATA_DIR", ".sac")),
        )
    return _SAC


# ─── Embedded HTTP server ────────────────────────────────────────


def _probe_existing_server(port: int) -> str:
    """Check if a healthy SaC server is already on this port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        try:
            probe.connect(("127.0.0.1", port))
        except OSError:
            return "free"
    try:
        import json
        import urllib.request
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=1.5
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict) and data.get("status") == "ok":
            return "sac"
    except Exception:
        return "foreign"
    return "foreign"


def _start_http_server(sac: SaC, port: int) -> str:
    """Start the HTTP server in a background thread, returning the base URL.

    If a healthy SaC server is already running on the port, reuse it.
    If the port is occupied by something else, try the next port.
    """
    global _HTTP_APP

    state = _probe_existing_server(port)
    if state == "sac":
        logger.info("Reusing existing SaC server at port %d", port)
        return f"http://127.0.0.1:{port}"

    if state == "foreign":
        port = port + 1
        logger.info("Port %d occupied, trying %d", port - 1, port)

    from sac.server.http.http import create_app
    app = create_app(sac)
    _HTTP_APP = app

    import uvicorn
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    # Wait for server to be ready
    import time
    for _ in range(50):
        if _probe_existing_server(port) == "sac":
            break
        time.sleep(0.1)

    return f"http://127.0.0.1:{port}"


def _ensure_http_server() -> str:
    """Ensure the embedded HTTP server is running, return base URL."""
    global _HTTP_BASE_URL
    if _HTTP_BASE_URL is not None:
        return _HTTP_BASE_URL
    port = int(os.environ.get("SAC_PORT", "8000"))
    _HTTP_BASE_URL = _start_http_server(_get_sac(), port)
    return _HTTP_BASE_URL


# ─── MCP Server ──────────────────────────────────────────────────


mcp = FastMCP(
    name="sac",
    instructions=(
        "Software as Content (SaC) — generate and evolve interactive applications "
        "in response to user intent.\n\n"
        "Workflow:\n"
        "1. Call `generate_app` with a user intent → get a viewer URL + TSX code\n"
        "2. Show the URL to the user so they can view and interact with the app\n"
        "3. Call `wait_for_action` to block until the user clicks a button in the app\n"
        "4. Process the returned action, compose updated content, call `evolve_app`\n"
        "5. Repeat from step 3\n\n"
        "The returned `code` field contains runnable TSX (React 19 + Tailwind + "
        "lucide-react + recharts). Hold onto `conversation_id` across turns."
    ),
)


def _post_inbox(base_url: str, payload: dict) -> dict:
    """POST to the embedded HTTP server's /inbox endpoint.

    Routes through the HTTP server so SSE subscribers (viewer) see
    streaming chunks, version events, etc. in real time.
    """
    import json
    import urllib.request

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/inbox",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    # /inbox can take 60-120s for LLM generation
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


@mcp.tool(
    name="generate_app",
    description=(
        "Generate the first version of an interactive app for a user intent. "
        "Returns a conversation_id and a viewer URL where the user can see "
        "and interact with the app. Use this when starting a new flow; if "
        "continuing an existing conversation, prefer evolve_app."
    ),
)
async def generate_app(
    intent: str,
    conversation_id: str | None = None,
) -> dict:
    base_url = _ensure_http_server()
    payload: dict[str, Any] = {"content": intent, "intent": intent}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _post_inbox, base_url, payload)
    return {
        "conversation_id": result.get("conversation_id"),
        "version": result.get("version"),
        "url": result.get("url", f"{base_url}/c/{result.get('conversation_id', '')}"),
        "type": result.get("type"),
    }


@mcp.tool(
    name="evolve_app",
    description=(
        "Evolve an existing app to a new version based on a follow-up intent. "
        "Requires a conversation_id from a prior generate_app call. The user's "
        "viewer updates in real-time as the new version streams in."
    ),
)
async def evolve_app(conversation_id: str, intent: str) -> dict:
    base_url = _ensure_http_server()
    payload: dict[str, Any] = {
        "conversation_id": conversation_id,
        "content": intent,
        "intent": intent,
    }
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _post_inbox, base_url, payload)
    return {
        "conversation_id": result.get("conversation_id"),
        "version": result.get("version"),
        "url": result.get("url", f"{base_url}/c/{conversation_id}"),
        "type": result.get("type"),
    }


@mcp.tool(
    name="wait_for_action",
    description=(
        "Block until the user performs an action in the viewer app (clicks a "
        "button, submits a form, or types in the chat panel). Returns the "
        "action intent and optional context. Use this after generate_app or "
        "evolve_app to receive interactive feedback. Times out after the "
        "specified duration (default 5 minutes) — a timeout means the user "
        "hasn't interacted yet, and you can call wait_for_action again."
    ),
)
async def wait_for_action(
    conversation_id: str,
    timeout: float = 300.0,
) -> dict:
    base_url = _ensure_http_server()
    timeout = min(max(timeout, 1.0), 600.0)

    # Long-poll the HTTP server's /wait-action endpoint.
    # This works whether the HTTP server is embedded or external.
    import json
    import urllib.request
    url = f"{base_url}/c/{conversation_id}/wait-action?timeout={timeout}"
    loop = asyncio.get_event_loop()
    try:
        def _poll():
            with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        return await loop.run_in_executor(None, _poll)
    except Exception:
        return {"action": None, "timed_out": True}


def _http_get(path: str) -> dict:
    """GET from the embedded HTTP server."""
    import json
    import urllib.request
    base_url = _ensure_http_server()
    with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


@mcp.tool(
    name="list_conversations",
    description="List all conversations persisted by this SaC instance.",
)
async def list_conversations() -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _http_get, "/conversations")


@mcp.tool(
    name="get_conversation",
    description=(
        "Fetch the full state of a conversation by id, including the latest app "
        "code, viewer URL, and a summary of its event history."
    ),
)
async def get_conversation(conversation_id: str) -> dict:
    base_url = _ensure_http_server()
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, _http_get, f"/conversations/{conversation_id}"
    )
    conv = data.get("conversation", {})
    conv["url"] = f"{base_url}/c/{conversation_id}"
    return conv


# ─── Entry Point ─────────────────────────────────────────────────


def run_stdio() -> None:
    """Run the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
