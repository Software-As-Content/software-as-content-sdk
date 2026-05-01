"""
MCP Server — exposes the SaC SDK as Model Context Protocol tools.

Launch via:
    sac serve --transport stdio

Tools exposed:
    generate_app(intent, conversation_id?, web_search?)
        → first version of an app for a given intent. Returns conversation_id
          for chaining subsequent evolve calls.

    evolve_app(conversation_id, intent)
        → next version of an app, evolved from the current state. SaC decides
          whether to extend the current view or add a new section.

    list_conversations()
        → all conversations persisted by this SaC instance.

    get_conversation(conversation_id)
        → full state of one conversation (latest code + history).

Conventions:
  - Conversation state is owned by the host: pass `conversation_id` to chain calls.
  - Persistence uses FileStore at $SAC_DATA_DIR (default: ./.sac/), so state
    survives across MCP server restarts.
  - Returned `code` is runnable TSX (React 19 + Tailwind + lucide-react + recharts).
    Hosts that can render TSX render directly; others can show as text.

Required env:
  - SAC_API_KEY            OpenRouter API key
  - SAC_SEARCH_API_KEY     (optional) Tavily key — enables web search
  - SAC_DATA_DIR           (optional) where to persist conversations (default: .sac)
  - SAC_MODEL              (optional) default model id
"""

from __future__ import annotations

import os
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


# ─── Process-wide SaC instance + Conversation cache ────────────────


_SAC: SaC | None = None
_CONVERSATIONS: dict[str, Any] = {}


def _get_sac() -> SaC:
    """Lazy-construct a process-wide SaC instance from environment variables."""
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


async def _get_or_load_conv(conv_id: str | None):
    """Return a live Conversation instance, loading from store if necessary."""
    sac = _get_sac()
    if conv_id and conv_id in _CONVERSATIONS:
        return _CONVERSATIONS[conv_id]
    conv = sac.conversation(id=conv_id)
    if conv_id:
        # Hydrate state (current_app, history) from the store
        await conv._load_from_store()
    _CONVERSATIONS[conv.id] = conv
    return conv


# ─── MCP Server ────────────────────────────────────────────────────


mcp = FastMCP(
    name="sac",
    instructions=(
        "Software as Content (SaC) — generate and evolve interactive applications "
        "in response to user intent. Use `generate_app` for a fresh intent. To "
        "continue refining a previous app, use `evolve_app` with the same "
        "conversation_id. The returned `code` field contains runnable TSX "
        "(React 19 + Tailwind + lucide-react + recharts) that you can render "
        "directly to the user. Hold onto `conversation_id` across turns to "
        "preserve state."
    ),
)


@mcp.tool(
    name="generate_app",
    description=(
        "Generate the first version of an interactive app for a user intent. "
        "Returns runnable TSX code and a conversation_id to use in subsequent "
        "evolve_app calls. Use this when starting a new flow; if continuing an "
        "existing conversation, prefer evolve_app."
    ),
)
async def generate_app(
    intent: str,
    conversation_id: str | None = None,
    web_search: bool = True,
) -> dict:
    conv = await _get_or_load_conv(conversation_id)
    app = await conv.generate(intent, web_search=web_search)
    return {
        "conversation_id": conv.id,
        "version": app.version,
        "code": app.code,
        "intent": app.intent,
        "suggestions": [
            {"label": s.label, "prompt": s.prompt, "type": s.type.value}
            for s in app.suggestions
        ],
        "search_results": [
            {
                "query": r.query,
                "answer": r.answer,
                "sources": [{"title": s.title, "url": s.url} for s in r.sources],
            }
            for r in app.search_results
        ],
    }


@mcp.tool(
    name="evolve_app",
    description=(
        "Evolve an existing app to a new version based on a follow-up intent. "
        "SaC inspects the current app and decides whether to extend the existing "
        "view (extend_current) or add a new section (new_page). Requires a "
        "conversation_id from a prior generate_app or evolve_app call."
    ),
)
async def evolve_app(conversation_id: str, intent: str) -> dict:
    conv = await _get_or_load_conv(conversation_id)
    app = await conv.evolve(intent)
    return {
        "conversation_id": conv.id,
        "version": app.version,
        "code": app.code,
        "intent": app.intent,
        "growth_decision": (
            {
                "growth_type": app.growth_decision.growth_type.value,
                "reason": app.growth_decision.reason,
            }
            if app.growth_decision
            else None
        ),
        "suggestions": [
            {"label": s.label, "prompt": s.prompt, "type": s.type.value}
            for s in app.suggestions
        ],
    }


@mcp.tool(
    name="list_conversations",
    description="List all conversations persisted by this SaC instance.",
)
async def list_conversations() -> dict:
    sac = _get_sac()
    convs = await sac._store.list_conversations()
    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "event_count": c.event_count,
                "updated_at": c.updated_at,
                "model": c.model,
            }
            for c in convs
        ]
    }


@mcp.tool(
    name="get_conversation",
    description=(
        "Fetch the full state of a conversation by id, including the latest app "
        "code and a summary of its event history."
    ),
)
async def get_conversation(conversation_id: str) -> dict:
    sac = _get_sac()
    conv_data = await sac._store.get_conversation(conversation_id)
    if conv_data is None:
        raise ValueError(f"Conversation not found: {conversation_id}")
    events = await sac._store.get_events(conversation_id)
    return {
        "id": conv_data.id,
        "title": conv_data.title,
        "created_at": conv_data.created_at,
        "updated_at": conv_data.updated_at,
        "model": conv_data.model,
        "latest_code": conv_data.latest_code,
        "latest_intent": conv_data.latest_intent,
        "event_count": conv_data.event_count,
        "history": [
            {"type": e.type, "timestamp": e.timestamp}
            for e in events
        ],
    }


# ─── Entry Point ────────────────────────────────────────────────


def run_stdio() -> None:
    """Run the MCP server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
