"""
HTTP/SSE Server

FastAPI app that exposes the SaC SDK as an HTTP service.
Requires: pip install sac-sdk[server]
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse
    from pydantic import BaseModel
    from sse_starlette.sse import EventSourceResponse
except ImportError as e:
    raise ImportError(
        "Server dependencies not installed. Run: pip install sac-sdk[server]"
    ) from e

from sac.runtime.prompts.app import AVAILABLE_MODELS, DEFAULT_MODEL
from sac.runtime.store.file import FileStore
from sac.sac import SaC
from sac.types import ConversationSettings

_STATIC_DIR = Path(__file__).parent / "static"
_RENDERER_DIR = Path(__file__).parent.parent / "renderer"

_VERSION = "0.1.0"


# ─── Request/Response Models ──────────────────────────────────────


class GenerateRequest(BaseModel):
    intent: str
    model: str | None = None
    conversation_id: str | None = None
    web_search: bool = True
    custom_instructions: str = ""
    use_design_system: bool = True


class EvolveRequest(BaseModel):
    intent: str
    conversation_id: str
    model: str | None = None


class StreamRequest(BaseModel):
    intent: str
    conversation_id: str | None = None
    model: str | None = None
    web_search: bool | None = None
    custom_instructions: str | None = None
    use_design_system: bool | None = None


class SendRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    model: str | None = None
    web_search: bool | None = None
    custom_instructions: str | None = None
    use_design_system: bool | None = None


class UpdateConversationRequest(BaseModel):
    title: str | None = None
    settings: dict[str, Any] | None = None


# ─── App Factory ──────────────────────────────────────────────────


def create_app(sac: SaC | None = None) -> FastAPI:
    """
    Create a FastAPI app wired to a SaC instance.

    If no SaC instance is provided, one is created from environment variables:
      - SAC_API_KEY (required) — OpenRouter API key
      - SAC_SEARCH_API_KEY (optional) — Tavily API key
      - SAC_MODEL (optional) — default model
    """
    if sac is None:
        api_key = os.environ.get("SAC_API_KEY", "")
        if not api_key:
            raise ValueError("SAC_API_KEY environment variable is required")
        data_dir = os.environ.get("SAC_DATA_DIR", ".sac")
        sac = SaC(
            api_key=api_key,
            search_api_key=os.environ.get("SAC_SEARCH_API_KEY"),
            model=os.environ.get("SAC_MODEL", DEFAULT_MODEL),
            store=FileStore(data_dir),
        )

    app = FastAPI(title="SaC SDK Server", version=_VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Keep track of active conversations
    _conversations: dict[str, Any] = {}

    async def _get_or_create_conv(conv_id: str | None, settings: ConversationSettings | None = None) -> Any:
        if conv_id and conv_id in _conversations:
            return _conversations[conv_id]
        conv = sac.conversation(id=conv_id, settings=settings)
        # If an existing conv_id was provided, load state from store
        if conv_id:
            await conv._load_from_store()
        _conversations[conv.id] = conv
        return conv

    # ─── Health & Discovery ──────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": _VERSION}

    @app.get("/models")
    async def list_models() -> dict[str, Any]:
        return {
            "models": [m.model_dump() for m in AVAILABLE_MODELS],
            "default": DEFAULT_MODEL,
        }

    # ─── Generation ──────────────────────────────────────────────

    @app.post("/generate")
    async def generate(req: GenerateRequest) -> dict[str, Any]:
        settings = ConversationSettings(
            custom_instructions=req.custom_instructions,
            use_design_system=req.use_design_system,
            enable_web_search=req.web_search,
        )
        conv = await _get_or_create_conv(req.conversation_id, settings)

        opts: dict[str, object] = {}
        if req.model:
            opts["model"] = req.model
        app_result = await conv.generate(req.intent, **opts)
        return {
            "success": True,
            "conversation_id": conv.id,
            "app": app_result.model_dump(),
        }

    @app.post("/evolve")
    async def evolve(req: EvolveRequest) -> dict[str, Any]:
        if req.conversation_id not in _conversations:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv = _conversations[req.conversation_id]

        opts: dict[str, object] = {}
        if req.model:
            opts["model"] = req.model
        app_result = await conv.evolve(req.intent, **opts)
        return {
            "success": True,
            "conversation_id": conv.id,
            "app": app_result.model_dump(),
        }

    @app.post("/stream")
    async def stream_generate(req: StreamRequest) -> EventSourceResponse:
        settings: ConversationSettings | None = None
        if req.web_search is not None or req.custom_instructions is not None or req.use_design_system is not None:
            settings = ConversationSettings(
                custom_instructions=req.custom_instructions or "",
                use_design_system=req.use_design_system if req.use_design_system is not None else True,
                enable_web_search=req.web_search if req.web_search is not None else True,
            )

        conv = await _get_or_create_conv(req.conversation_id, settings)

        opts: dict[str, object] = {}
        if req.model:
            opts["model"] = req.model

        async def event_generator():
            async for event in conv.stream(req.intent, **opts):
                payload = event.model_dump()
                # Attach conversation_id to complete events
                if event.type == "complete":
                    payload["conversation_id"] = conv.id
                yield {"event": event.type, "data": json.dumps(payload)}

        return EventSourceResponse(event_generator())

    @app.post("/send")
    async def send_message(req: SendRequest) -> dict[str, Any]:
        """
        Unified entry point. Classifies the message and either:
        - Returns a chat reply directly (type: "chat")
        - Returns classification only (type: "generate" or "evolve") —
          caller should then use /stream to execute
        """
        settings: ConversationSettings | None = None
        if req.web_search is not None or req.custom_instructions is not None or req.use_design_system is not None:
            settings = ConversationSettings(
                custom_instructions=req.custom_instructions or "",
                use_design_system=req.use_design_system if req.use_design_system is not None else True,
                enable_web_search=req.web_search if req.web_search is not None else True,
            )

        conv = await _get_or_create_conv(req.conversation_id, settings)

        classification = await conv.classify(req.message)

        if classification["type"] == "chat":
            reply = classification.get("reply", "")
            # Store user message and assistant reply
            from sac.types import MessageEvent
            await sac._store.add_event(
                MessageEvent(conversation_id=conv.id, role="user", content=req.message)
            )
            await sac._store.add_event(
                MessageEvent(conversation_id=conv.id, role="assistant", content=reply)
            )
            # Set title from first message if not already set
            conv_data = await sac._store.get_conversation(conv.id)
            if conv_data and not conv_data.title:
                title = req.message[:80] + ("..." if len(req.message) > 80 else "")
                await sac._store.update_conversation(conv.id, title=title)
            return {
                "type": "chat",
                "conversation_id": conv.id,
                "reply": reply,
            }

        # It's an "update" — return classification, let frontend call /stream
        # Set title from first message if not already set
        conv_data = await sac._store.get_conversation(conv.id)
        if conv_data and not conv_data.title:
            title = req.message[:80] + ("..." if len(req.message) > 80 else "")
            await sac._store.update_conversation(conv.id, title=title)

        action = "evolve" if conv.current_app else "generate"
        return {
            "type": action,
            "conversation_id": conv.id,
        }

    # ─── Conversation Management ─────────────────────────────────

    @app.get("/conversations")
    async def list_conversations() -> dict[str, Any]:
        convs = await sac._store.list_conversations()
        return {"conversations": [c.model_dump() for c in convs]}

    @app.get("/conversations/{conv_id}")
    async def get_conversation(conv_id: str) -> dict[str, Any]:
        conv = await sac._store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        events = await sac._store.get_events(conv_id)
        return {
            "conversation": conv.model_dump(),
            "events": [e.model_dump() for e in events],
        }

    @app.patch("/conversations/{conv_id}")
    async def update_conversation(conv_id: str, req: UpdateConversationRequest) -> dict[str, Any]:
        conv = await sac._store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        updates: dict[str, object] = {}
        if req.title is not None:
            updates["title"] = req.title
        if req.settings is not None:
            # Merge with existing settings
            current_settings = conv.settings.model_dump()
            current_settings.update(req.settings)
            updates["settings"] = ConversationSettings(**current_settings)
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await sac._store.update_conversation(conv_id, **updates)

        updated = await sac._store.get_conversation(conv_id)
        return {"conversation": updated.model_dump() if updated else conv.model_dump()}

    @app.delete("/conversations/{conv_id}")
    async def delete_conversation(conv_id: str) -> dict[str, bool]:
        conv = await sac._store.get_conversation(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        await sac._store.delete_conversation(conv_id)
        # Also remove from active conversations cache
        _conversations.pop(conv_id, None)
        return {"success": True}

    # ─── Web Preview UI ─────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def preview_page():
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/renderer/{path:path}")
    async def serve_renderer(path: str):
        file = _RENDERER_DIR / path
        if not file.exists() or not file.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        suffix = file.suffix
        media_types = {
            ".html": "text/html",
            ".js": "application/javascript",
            ".md": "text/markdown",
            ".css": "text/css",
        }
        return FileResponse(file, media_type=media_types.get(suffix, "application/octet-stream"))

    return app


# ─── Standalone runner ────────────────────────────────────────────


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the server with uvicorn."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
