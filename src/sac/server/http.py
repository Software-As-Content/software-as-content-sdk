"""
HTTP/SSE Server

FastAPI app that exposes the SaC SDK as an HTTP service.
Requires: pip install sac-sdk[server]
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import httpx
    from fastapi import FastAPI, HTTPException, Request
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


# ─── OpenClaw Gateway WebSocket RPC ─────────────────────────────


async def _openclaw_gateway_send(
    ws_url: str,
    token: str,
    session_key: str,
    message: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send a message to an OpenClaw agent session via Gateway WebSocket RPC.

    Implements the connect-request-disconnect pattern:
      1. Connect to gateway WebSocket
      2. Receive connect.challenge event
      3. Send connect request with auth token
      4. Receive hello-ok response
      5. Send sessions.send request
      6. Receive response and disconnect

    Args:
        ws_url: Gateway WebSocket URL (e.g. "ws://127.0.0.1:18789")
        token: Gateway auth token
        session_key: Target session key (e.g. "agent:main:main")
        message: Message text to send
        timeout: Overall timeout in seconds
    """
    try:
        import websockets
    except ImportError:
        raise RuntimeError(
            "websockets package required for OpenClaw callback. "
            "Install with: pip install websockets"
        )

    async with websockets.connect(ws_url, max_size=25 * 1024 * 1024) as ws:
        # Step 1: Receive connect.challenge
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        challenge = json.loads(raw)
        if challenge.get("event") != "connect.challenge":
            raise RuntimeError(f"Expected connect.challenge, got: {challenge}")

        # Step 2: Send connect request
        connect_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": "gateway-client",
                    "version": "0.1.0",
                    "platform": "sac-sdk",
                    "mode": "backend",
                },
                "caps": [],
                "role": "operator",
                "scopes": ["operator.write"],
                "auth": {"token": token},
            },
        }))

        # Step 3: Receive hello-ok
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        hello = json.loads(raw)
        if not (hello.get("type") == "res" and hello.get("ok")):
            raise RuntimeError(f"Gateway auth failed: {hello}")

        # Step 4: Send sessions.send
        send_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "type": "req",
            "id": send_id,
            "method": "sessions.send",
            "params": {
                "key": session_key,
                "message": message,
                "idempotencyKey": str(uuid.uuid4()),
            },
        }))

        # Step 5: Wait for response (skip events/ticks)
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            frame = json.loads(raw)
            if frame.get("type") == "res" and frame.get("id") == send_id:
                if frame.get("ok"):
                    return frame.get("payload", {})
                else:
                    raise RuntimeError(f"sessions.send failed: {frame.get('error')}")
            # Skip unsolicited events (ticks, etc.)


# ─── Pub/Sub for SSE conversation updates ────────────────────────


class _PubSub:
    """In-memory per-conversation event broker for SSE subscribers.

    One SaC server process manages all subscribers. For multi-process
    deployments swap this for redis/nats; the publish/subscribe surface
    stays the same.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, conv_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subs[conv_id].append(q)
        return q

    def unsubscribe(self, conv_id: str, q: asyncio.Queue) -> None:
        if conv_id in self._subs:
            try:
                self._subs[conv_id].remove(q)
            except ValueError:
                pass
            if not self._subs[conv_id]:
                del self._subs[conv_id]

    def publish(self, conv_id: str, event_type: str, data: dict[str, Any]) -> None:
        payload = {"event": event_type, "data": json.dumps(data)}
        for q in list(self._subs.get(conv_id, [])):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow consumer — drop silently rather than block agent flow.
                pass


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


class InboxRequest(BaseModel):
    """Protocol contract: upstream agent posts content for SaC to render.

    - `content`: the actual data the agent wants rendered (any string form).
    - `intent`: optional human-readable label/hint for the rendering brain.
    - `conversation_id`: omit for first call; include to evolve an existing
      conversation. SaC decides generate vs evolve based on conversation state.
    - `callback_url`: where SaC should POST user actions (button clicks,
      follow-up intents). Set on first call; subsequent calls may omit.
    - `suggestions`: optional list of follow-up actions (label/prompt/type)
      the agent wants to expose. If omitted, SaC's default agent generates
      content-grounded suggestions automatically.
    - `context`: opaque metadata echoed back on callbacks; SaC does not parse.
    """

    content: str
    intent: str | None = None
    conversation_id: str | None = None
    callback_url: str | None = None
    callback_format: str | None = None  # "default" | "openclaw_gateway" | "codex_exec_resume"
    callback_auth: str | None = None    # e.g. "Bearer <token>"
    suggestions: list[dict[str, Any]] | None = None
    context: dict[str, Any] | None = None


class ActionRequest(BaseModel):
    """User action (button click in App, or text input in chat panel) that
    SaC forwards to the conversation's registered callback_url.

    - `intent`: human-readable description of what the user did/said.
    - `context`: opaque metadata to attach (echoed to the agent).
    """

    intent: str
    context: dict[str, Any] | None = None


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

    server_cwd = Path.cwd()
    app = FastAPI(title="SaC SDK Server", version=_VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Keep track of active conversations
    _conversations: dict[str, Any] = {}

    # Pub/sub broker for /c/{id}/events SSE subscribers
    pubsub = _PubSub()

    def _get_user_id(request: Request) -> str:
        """Extract user ID from X-User-Id header, default to 'anonymous'."""
        return request.headers.get("x-user-id", "anonymous")

    def _resolve_codex_cwd(raw_cwd: str) -> str | None:
        """Resolve the working directory for Codex callback subprocesses.

        Omitting `cwd` preserves Codex's stored thread cwd. `cwd=server`
        means "use the directory where `sac serve` was started".
        For the Codex MVP this is usually the safest value because generated
        apps may be created from transient Codex artifact/session directories.
        If a callback gives a directory that does not look like a project root
        while the server cwd does, prefer the server cwd.
        """
        value = raw_cwd.strip()
        if not value:
            return None
        if value in {"server", "."}:
            return str(server_cwd)

        path = Path(value).expanduser()
        if not path.is_dir():
            return str(server_cwd)

        project_markers = (".git", "pyproject.toml", "package.json", "src")
        looks_like_project = any((path / marker).exists() for marker in project_markers)
        server_looks_like_project = any(
            (server_cwd / marker).exists() for marker in project_markers
        )
        if not looks_like_project and server_looks_like_project:
            return str(server_cwd)

        return str(path)

    def _publish_callback_failure(conv_id: str, message: str) -> None:
        pubsub.publish(
            conv_id,
            "chat",
            {
                "role": "system",
                "content": message,
            },
        )

    def _resolve_codex_bin() -> str:
        configured = os.environ.get("SAC_CODEX_BIN", "").strip()
        if configured:
            return configured

        found = shutil.which("codex")
        if found:
            return found

        app_bundle_bin = Path("/Applications/Codex.app/Contents/Resources/codex")
        if app_bundle_bin.exists():
            return str(app_bundle_bin)

        return "codex"

    async def _get_or_create_conv(conv_id: str | None, settings: ConversationSettings | None = None, user_id: str = "") -> Any:
        if conv_id and conv_id in _conversations:
            return _conversations[conv_id]
        conv = sac.conversation(id=conv_id, settings=settings)
        if user_id:
            conv._data.user_id = user_id
        # If an existing conv_id was provided, load state from store
        if conv_id:
            await conv._load_from_store()
        else:
            # Brand-new conversation: `sac.conversation()` schedules creation
            # as a fire-and-forget task. Explicitly await it here so the conv
            # is fully registered in the store BEFORE any subsequent
            # update_conversation calls (e.g. callback_url persistence in
            # /inbox). create_conversation is idempotent — safe to call again.
            await sac._store.create_conversation(conv._data)
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
    async def generate(req: GenerateRequest, request: Request) -> dict[str, Any]:
        settings = ConversationSettings(
            custom_instructions=req.custom_instructions,
            use_design_system=req.use_design_system,
            enable_web_search=req.web_search,
        )
        conv = await _get_or_create_conv(req.conversation_id, settings, user_id=_get_user_id(request))

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
    async def stream_generate(req: StreamRequest, request: Request) -> EventSourceResponse:
        settings: ConversationSettings | None = None
        if req.web_search is not None or req.custom_instructions is not None or req.use_design_system is not None:
            settings = ConversationSettings(
                custom_instructions=req.custom_instructions or "",
                use_design_system=req.use_design_system if req.use_design_system is not None else True,
                enable_web_search=req.web_search if req.web_search is not None else True,
            )

        conv = await _get_or_create_conv(req.conversation_id, settings, user_id=_get_user_id(request))

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
    async def send_message(req: SendRequest, request: Request) -> dict[str, Any]:
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

        conv = await _get_or_create_conv(req.conversation_id, settings, user_id=_get_user_id(request))

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

    # ─── Protocol: /inbox (upstream agent → SaC) ─────────────────

    @app.post("/inbox")
    async def inbox(req: InboxRequest, request: Request) -> dict[str, Any]:
        """Receive content from an upstream agent and render it.

        SaC inspects the response shape and dispatches to one of two channels:
          - Φⁿˡ (chat) — short / conversational response → assistant message
            in the NL chat panel; no new App version.
          - Φˢ  (ui)   — substantive content → render as new App version
            (generate first, evolve subsequently).

        The chat-vs-ui decision currently reuses the LegacyShim classifier
        (small extra LLM call). A future fused-LLM-call milestone collapses
        this into one call alongside code generation.

        Returns conversation_id, the URL to view, version (null for chat-
        only responses), and `type` indicating which channel was used.
        """
        from sac.types import MessageEvent

        conv = await _get_or_create_conv(req.conversation_id, user_id=_get_user_id(request))

        # Persist callback settings on the conversation so future user actions
        # know where and how to POST. First call sets them; later calls may update.
        callback_updates: dict[str, Any] = {}
        if req.callback_url:
            callback_updates["callback_url"] = req.callback_url
        if req.callback_format:
            callback_updates["callback_format"] = req.callback_format
        if req.callback_auth:
            callback_updates["callback_auth"] = req.callback_auth
        if callback_updates:
            await sac._store.update_conversation(conv.id, **callback_updates)

        base = str(request.base_url).rstrip("/")

        # Classify response shape: chat (NL) vs update (Φˢ render).
        classification = await sac._legacy_shim.classify(conv, req.content)

        if classification["type"] == "chat":
            # Show the agent's content directly as an assistant message in
            # the NL channel. We ignore classify's generated `reply` field —
            # that was meant for the legacy "assistant replies to user
            # message" flow; here the agent IS the message.
            await sac._store.add_event(
                MessageEvent(
                    conversation_id=conv.id,
                    role="assistant",
                    content=req.content,
                )
            )
            pubsub.publish(
                conv.id,
                "chat",
                {"role": "assistant", "content": req.content},
            )
            return {
                "conversation_id": conv.id,
                "url": f"{base}/c/{conv.id}",
                "version": None,
                "type": "chat",
            }

        # Φˢ — render new App version directly via conv.ingest()
        # No StandaloneAgent detour — /inbox owns event recording here.
        from sac.types import (
            EventStatus,
            GenerationEvent,
            GrowthEvent,
            IntentSuggestion,
        )
        from sac.builtin.prompts.intent import (
            get_intent_suggestion_prompt,
            parse_intent_suggestions,
        )
        from sac.types import Message as SaCMessage

        intent = req.intent or req.content[:200]
        is_evolve = conv.current_app is not None

        # Record user intent as a message event
        await sac._store.add_event(
            MessageEvent(conversation_id=conv.id, role="user", content=intent)
        )

        try:
            app_result = await conv.ingest(
                content=req.content, intent=intent
            )

            # Suggestions: use agent-provided override, or generate defaults
            if req.suggestions is not None:
                try:
                    suggestions = [IntentSuggestion(**s) for s in req.suggestions]
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid suggestions payload: {e}",
                    )
            else:
                try:
                    prompt = get_intent_suggestion_prompt(
                        intent, [], conv.settings.intent_rules
                    )
                    response = await sac._llm.complete(
                        conv.model,
                        [SaCMessage(role="user", content=prompt)],
                    )
                    suggestions = parse_intent_suggestions(response)
                except Exception:
                    suggestions = []

            app_result.suggestions = suggestions

            event_cls = GrowthEvent if is_evolve else GenerationEvent
            await sac._store.add_event(
                event_cls(
                    conversation_id=conv.id,
                    intent=intent,
                    model=conv.model,
                    status=EventStatus.SUCCESS,
                    code=app_result.code,
                    stages=app_result.stages,
                    intent_suggestions=suggestions or None,
                )
            )

            # Set title from first generation
            if not is_evolve and conv.version == 1:
                title = intent[:80] + ("..." if len(intent) > 80 else "")
                await sac._store.update_conversation(conv.id, title=title)

        except HTTPException:
            raise
        except Exception as exc:
            event_cls = GrowthEvent if is_evolve else GenerationEvent
            await sac._store.add_event(
                event_cls(
                    conversation_id=conv.id,
                    intent=intent,
                    model=conv.model,
                    status=EventStatus.ERROR,
                    error=str(exc),
                )
            )
            raise HTTPException(status_code=500, detail=str(exc))

        pubsub.publish(
            conv.id,
            "version",
            {
                "conversation_id": conv.id,
                "version": app_result.version,
            },
        )

        return {
            "conversation_id": conv.id,
            "url": f"{base}/c/{conv.id}",
            "version": app_result.version,
            "type": "ui",
        }

    # ─── Protocol: /c/{id}/events (browser ← SaC live updates) ───

    @app.get("/c/{conv_id}/events")
    async def conversation_events(conv_id: str, request: Request) -> EventSourceResponse:
        """SSE stream of conversation updates.

        Emits events whenever the conversation gets new state from /inbox:
          - `version` — new App version produced (browser should reload App)
          - `chat`    — new assistant message (browser should append bubble)

        Browser fetches initial state via GET /c/{conv_id} or similar; SSE
        only delivers deltas. Sends a 15-second keepalive `ping` to survive
        proxies that drop idle connections.
        """
        conv_data = await sac._store.get_conversation(conv_id)
        if conv_data is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        q = pubsub.subscribe(conv_id)

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield event
                    except asyncio.TimeoutError:
                        # Keepalive — many proxies kill idle SSE after ~30s.
                        yield {"event": "ping", "data": "{}"}
            finally:
                pubsub.unsubscribe(conv_id, q)

        return EventSourceResponse(event_generator())

    @app.post("/c/{conv_id}/action")
    async def conversation_action(conv_id: str, req: ActionRequest, request: Request) -> dict[str, Any]:
        """Forward a user action to the agent's registered callback_url.

        Called by the SaC viewer when the user clicks a button (sac-action
        message from the iframe) or types into the chat panel. SaC just
        relays — the agent is expected to ack quickly, do its work
        asynchronously, then POST a new response back to /inbox.
        """
        conv_data = await sac._store.get_conversation(conv_id)
        if conv_data is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if not conv_data.callback_url:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No callback_url registered on this conversation. The "
                    "agent must include callback_url in its first /inbox call."
                ),
            )

        # Route callback based on format
        sac_url = str(request.base_url).rstrip("/")
        fmt = conv_data.callback_format or "default"
        callback_scheme = urlparse(conv_data.callback_url).scheme
        if fmt == "default" and callback_scheme == "codex":
            fmt = "codex_exec_resume"
        elif fmt == "default" and callback_scheme in ("ws", "wss"):
            fmt = "openclaw_gateway"

        if fmt == "openclaw_gateway":
            # OpenClaw Gateway: send message via WebSocket RPC.
            # callback_url format: ws://host:port?session=<session_key>
            # callback_auth format: Bearer <gateway_token>
            parsed = urlparse(conv_data.callback_url)
            qs = parse_qs(parsed.query)
            session_key = (qs.get("session") or ["agent:main:main"])[0]
            # Reconstruct clean WebSocket URL without query params
            ws_url = f"{parsed.scheme}://{parsed.netloc}"

            token = ""
            if conv_data.callback_auth:
                # Strip "Bearer " prefix if present
                auth = conv_data.callback_auth
                token = auth.removeprefix("Bearer ").strip()

            message = (
                f"A user is viewing a SaC interactive app and requested: {req.intent}\n\n"
                f"Compose rich, detailed content for this request, then run this exact command "
                f"(replace CONTENT with your composed content, escape quotes and newlines for JSON):\n\n"
                f'exec: curl -s -X POST "{sac_url}/inbox" '
                f'-H "Content-Type: application/json" '
                f"-d '{{\"conversation_id\": \"{conv_id}\", "
                f"\"content\": \"CONTENT\", "
                f"\"intent\": \"{req.intent}\"}}'\n\n"
                f"Do NOT ask clarifying questions — just compose the best content you can and run the curl command."
            )

            try:
                await _openclaw_gateway_send(
                    ws_url=ws_url,
                    token=token,
                    session_key=session_key,
                    message=message,
                )
            except Exception as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to send to OpenClaw gateway ({ws_url}): {e}",
                )

        elif fmt == "codex_exec_resume":
            # Codex CLI adapter: resume an existing Codex thread and send the
            # SaC action as the next user prompt. This is intentionally a thin
            # platform adapter, analogous to OpenClaw's gateway `sessions.send`.
            parsed = urlparse(conv_data.callback_url)
            if parsed.scheme != "codex" or parsed.netloc != "resume":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Invalid Codex callback_url. Expected "
                        "codex://resume?thread=<thread_id>&cwd=<absolute_path>."
                    ),
                )
            qs = parse_qs(parsed.query)
            thread_id = (qs.get("thread") or qs.get("thread_id") or [""])[0].strip()
            cwd = _resolve_codex_cwd((qs.get("cwd") or [""])[0])
            if not thread_id:
                raise HTTPException(
                    status_code=400,
                    detail="Codex callback_url must include thread=<thread_id>.",
                )

            context_text = ""
            if req.context is not None:
                context_text = (
                    "\n\nAction context JSON:\n"
                    f"```json\n{json.dumps(req.context, ensure_ascii=False, indent=2)}\n```"
                )

            message = (
                f"A user is viewing a SaC interactive app and requested: {req.intent}"
                f"{context_text}\n\n"
                f"Continue the engineering analysis for this SaC conversation. "
                f"Use the existing repository/session context first; do not run broad validation "
                f"or debug unrelated infrastructure unless the requested action explicitly asks for it. "
                f"Compose rich, detailed content for the request, then run this exact command "
                f"(replace CONTENT with your composed content, escape quotes and newlines for JSON):\n\n"
                f'curl -s -X POST "{sac_url}/inbox" '
                f'-H "Content-Type: application/json" '
                f"-d '{{\"conversation_id\": \"{conv_id}\", "
                f"\"content\": \"CONTENT\", "
                f"\"intent\": \"{req.intent}\"}}'\n\n"
                f"Do NOT ask clarifying questions. Do NOT only reply in chat. "
                f"Do the best follow-up analysis you can and update the SaC app via /inbox."
            )

            async def _run_codex_resume() -> None:
                codex_bin = _resolve_codex_bin()
                cmd = [codex_bin]
                if cwd:
                    cmd.extend(["-C", cwd])
                cmd.extend(["exec", "resume"])
                if thread_id == "last":
                    cmd.append("--last")
                else:
                    cmd.append(thread_id)
                cmd.append(message)

                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await proc.communicate()
                    if proc.returncode != 0:
                        stdout_tail = stdout.decode(errors="replace")[-4000:]
                        stderr_tail = stderr.decode(errors="replace")[-4000:]
                        print(
                            "codex_exec_resume failed",
                            {
                                "returncode": proc.returncode,
                                "cwd": cwd,
                                "stdout": stdout_tail,
                                "stderr": stderr_tail,
                            },
                        )
                        detail = stderr_tail or stdout_tail or f"exit code {proc.returncode}"
                        _publish_callback_failure(
                            conv_id,
                            f"Codex callback failed ({detail.strip()[:1200]}).",
                        )
                except FileNotFoundError:
                    print(f"codex_exec_resume failed: `{codex_bin}` command not found")
                    _publish_callback_failure(
                        conv_id,
                        (
                            "Codex callback failed: Codex CLI not found. "
                            "Set SAC_CODEX_BIN to the absolute codex executable path."
                        ),
                    )
                except Exception as exc:
                    print(f"codex_exec_resume failed: {exc}")
                    _publish_callback_failure(
                        conv_id,
                        f"Codex callback failed: {exc}",
                    )

            asyncio.create_task(_run_codex_resume())

        elif fmt == "openclaw_taskflow":
            # Legacy: OpenClaw webhook TaskFlow creation (kept for compat).
            payload: dict[str, Any] = {
                "action": "create_flow",
                "goal": (
                    f"SaC user action on conversation {conv_id}: "
                    f"{req.intent}\n\n"
                    f"Use the sac-interaction skill to POST updated content "
                    f"to {sac_url}/inbox with conversation_id \"{conv_id}\"."
                ),
            }
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if conv_data.callback_auth:
                headers["Authorization"] = conv_data.callback_auth
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    response = await client.post(
                        conv_data.callback_url, json=payload, headers=headers
                    )
                    response.raise_for_status()
                except httpx.HTTPError as e:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Failed to reach callback_url ({conv_data.callback_url}): {e}",
                    )

        else:
            # Default SaC protocol format (HTTP POST)
            payload_default: dict[str, Any] = {
                "conversation_id": conv_id,
                "intent": req.intent,
            }
            if req.context is not None:
                payload_default["context"] = req.context
            headers_default: dict[str, str] = {"Content-Type": "application/json"}
            if conv_data.callback_auth:
                headers_default["Authorization"] = conv_data.callback_auth
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    response = await client.post(
                        conv_data.callback_url, json=payload_default, headers=headers_default
                    )
                    response.raise_for_status()
                except httpx.HTTPError as e:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Failed to reach callback_url ({conv_data.callback_url}): {e}",
                    )

        return {"ok": True, "callback_url": conv_data.callback_url}

    # ─── Conversation Management ─────────────────────────────────

    @app.get("/conversations")
    async def list_conversations(request: Request) -> dict[str, Any]:
        user_id = _get_user_id(request)
        convs = await sac._store.list_conversations(user_id=user_id)
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

    @app.get("/c/{conv_id}", response_class=HTMLResponse)
    async def conversation_page(conv_id: str):
        """Pretty URL form for a specific conversation; serves the same viewer.

        The static page reads the conversation id from the URL path (or `?c=`
        query param) and auto-loads it on init.
        """
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
