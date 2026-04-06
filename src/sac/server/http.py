"""
HTTP/SSE Server

FastAPI app that exposes the SaC SDK as an HTTP service.
Requires: pip install sac-sdk[server]
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _load_dotenv() -> None:
    """Load .env file from project root if it exists."""
    env_file = Path(__file__).resolve().parents[3] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from sse_starlette.sse import EventSourceResponse
except ImportError as e:
    raise ImportError(
        "Server dependencies not installed. Run: pip install sac-sdk[server]"
    ) from e

from sac.client import SaC
from sac.types import ConversationSettings


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
        sac = SaC(
            api_key=api_key,
            search_api_key=os.environ.get("SAC_SEARCH_API_KEY"),
            model=os.environ.get("SAC_MODEL", "google/gemini-3-flash-preview"),
        )

    app = FastAPI(title="SaC SDK Server", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Keep track of active conversations
    _conversations: dict[str, Any] = {}

    def _get_or_create_conv(conv_id: str | None, settings: ConversationSettings | None = None) -> Any:
        if conv_id and conv_id in _conversations:
            return _conversations[conv_id]
        conv = sac.conversation(id=conv_id, settings=settings)
        _conversations[conv.id] = conv
        return conv

    @app.post("/generate")
    async def generate(req: GenerateRequest) -> dict[str, Any]:
        settings = ConversationSettings(
            custom_instructions=req.custom_instructions,
            use_design_system=req.use_design_system,
            enable_web_search=req.web_search,
        )
        conv = _get_or_create_conv(req.conversation_id, settings)

        app_result = await conv.generate(req.intent, model=req.model)
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

        app_result = await conv.evolve(req.intent, model=req.model)
        return {
            "success": True,
            "conversation_id": conv.id,
            "app": app_result.model_dump(),
        }

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

    @app.get("/stream")
    async def stream_generate(
        intent: str,
        conversation_id: str | None = None,
        model: str | None = None,
    ) -> EventSourceResponse:
        conv = _get_or_create_conv(conversation_id)

        async def event_generator():
            async for event in conv.stream(intent, model=model):
                yield {"data": json.dumps(event.model_dump())}

        return EventSourceResponse(event_generator())

    return app


# ─── Standalone runner ────────────────────────────────────────────


def run(host: str = "0.0.0.0", port: int = 3000) -> None:
    """Run the server with uvicorn."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
