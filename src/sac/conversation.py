"""
Conversation — the core stateful primitive of SaC.

Each Conversation instance represents a single session where UI is generated and evolved.
"""

from __future__ import annotations

from typing import AsyncIterator

import json

from sac.runtime.pipeline.evolve import evolve_pipeline, stream_evolve_pipeline
from sac.runtime.pipeline.generate import generate_pipeline, stream_generate_pipeline
from sac.runtime.prompts.app import DEFAULT_MODEL
from sac.runtime.prompts.classify import CLASSIFY_COLD, CLASSIFY_WITH_CONTEXT
from sac.runtime.providers.base import LLMProvider, SearchProvider
from sac.runtime.store.base import ConversationStore
from sac.types import (
    App,
    ConversationData,
    ConversationSettings,
    EventStatus,
    GenerationEvent,
    GrowthEvent,
    Message,
    MessageEvent,
    PipelineChunkEvent,
    PipelineCompleteEvent,
    PipelineErrorEvent,
    PipelineEvent,
    PipelineStageEvent,
    SendResult,
    SendResultType,
    StageStatus,
)


class Conversation:
    """
    A stateful conversation that generates and evolves UI through dialog.

    Usage:
        conv = sac.conversation()
        app = await conv.generate("travel guide for Hangzhou")
        app = await conv.evolve("add restaurant recommendations")
    """

    def __init__(
        self,
        data: ConversationData,
        llm: LLMProvider,
        search: SearchProvider | None,
        store: ConversationStore,
    ) -> None:
        self._data = data
        self._llm = llm
        self._search = search
        self._store = store
        self._apps: list[App] = []

    async def _load_from_store(self) -> None:
        """Load conversation state from store, rebuilding _apps from events."""
        stored = await self._store.get_conversation(self._data.id)
        if not stored:
            return

        # Restore conversation metadata
        self._data.title = stored.title
        self._data.model = stored.model or self._data.model
        if stored.settings:
            self._data.settings = stored.settings

        # Rebuild _apps from generation/growth events
        events = await self._store.get_events(self._data.id)
        self._apps = []
        for event in events:
            if hasattr(event, 'code') and event.code and hasattr(event, 'status'):
                if event.status == EventStatus.SUCCESS:
                    version = len(self._apps) + 1
                    intent = event.intent if hasattr(event, 'intent') else ""
                    self._apps.append(App(
                        version=version,
                        intent=intent,
                        code=event.code,
                        model=event.model if hasattr(event, 'model') else "",
                    ))

    # ─── Properties ────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return self._data.id

    @property
    def title(self) -> str:
        return self._data.title

    @property
    def settings(self) -> ConversationSettings:
        return self._data.settings

    @property
    def model(self) -> str:
        return self._data.model or DEFAULT_MODEL

    @property
    def current_app(self) -> App | None:
        return self._apps[-1] if self._apps else None

    @property
    def history(self) -> list[App]:
        return list(self._apps)

    @property
    def version(self) -> int:
        return len(self._apps)

    # ─── Unified Entry Point ─────────────────────────────────────────

    async def send(self, message: str, **opts: object) -> SendResult:
        """
        Unified entry point — the natural way to interact with a conversation.

        Classifies the message as chat, generate, or evolve, then routes accordingly:
          - chat → LLM replies with natural language, no app change
          - generate → creates a new app (first-time or fresh)
          - evolve → updates the existing app

        Returns:
            SendResult with type, optional reply (chat), optional app (generate/evolve)
        """
        classification = await self.classify(message)

        if classification["type"] == "chat":
            reply = classification.get("reply", "")

            # Store both user message and assistant reply
            await self._store.add_event(
                MessageEvent(conversation_id=self.id, role="user", content=message)
            )
            await self._store.add_event(
                MessageEvent(conversation_id=self.id, role="assistant", content=reply)
            )

            return SendResult(type=SendResultType.CHAT, reply=reply)

        # It's an "update" — route to generate or evolve
        if self._apps:
            app = await self.evolve(message, **opts)
            return SendResult(type=SendResultType.EVOLVE, app=app)
        else:
            app = await self.generate(message, **opts)
            return SendResult(type=SendResultType.GENERATE, app=app)

    async def classify(self, message: str) -> dict:
        """Classify a message as 'chat' or 'update' using LLM."""
        has_context = len(self._apps) > 0
        system_prompt = CLASSIFY_WITH_CONTEXT if has_context else CLASSIFY_COLD

        user_content = message
        if has_context and self.current_app:
            user_content = f"[Current app intent: {self.current_app.intent}]\n\nUser message: {message}"

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

        try:
            raw = await self._llm.complete(self.model, messages, max_tokens=256)
            # Strip markdown fences if present
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            # Default to update on parse failure
            return {"type": "update"}

    # ─── Core Methods ──────────────────────────────────────────────

    async def generate(self, intent: str, **opts: object) -> App:
        """Generate a new app from an intent (first-time or fresh generation)."""
        model = str(opts.get("model", self.model))
        web_search = opts.get("web_search", self.settings.enable_web_search)

        # Record user message
        await self._store.add_event(
            MessageEvent(conversation_id=self.id, role="user", content=intent)
        )

        # Override search setting if explicitly passed
        settings = self.settings.model_copy()
        if isinstance(web_search, bool):
            settings.enable_web_search = web_search

        try:
            app = await generate_pipeline(
                intent=intent,
                model=model,
                llm=self._llm,
                search=self._search if settings.enable_web_search else None,
                settings=settings,
                version=self.version + 1,
            )

            self._apps.append(app)

            # Record generation event (triggers store._write_output if configured)
            await self._store.add_event(
                GenerationEvent(
                    conversation_id=self.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.SUCCESS,
                    code=app.code,
                    stages=app.stages,
                    search_queries=app.search_queries or None,
                    search_results=app.search_results or None,
                    intent_suggestions=app.suggestions or None,
                )
            )

            # Update title on first generation
            if self.version == 1:
                title = intent[:80] + ("..." if len(intent) > 80 else "")
                await self._store.update_conversation(self.id, title=title)

            return app

        except Exception as exc:
            await self._store.add_event(
                GenerationEvent(
                    conversation_id=self.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.ERROR,
                    error=str(exc),
                )
            )
            raise

    async def evolve(self, intent: str, **opts: object) -> App:
        """Evolve the current app with a new intent."""
        if not self._apps:
            raise ValueError("No app to evolve. Call generate() first.")

        current = self.current_app
        assert current is not None

        model = str(opts.get("model", self.model))

        # Record user message
        await self._store.add_event(
            MessageEvent(conversation_id=self.id, role="user", content=intent)
        )

        try:
            app = await evolve_pipeline(
                new_intent=intent,
                current_code=current.code,
                original_intent=current.intent,
                model=model,
                llm=self._llm,
                search=self._search,
                settings=self.settings,
                version=self.version + 1,
                parent_version=current.version,
            )

            self._apps.append(app)

            # Record growth event (triggers store._write_output if configured)
            await self._store.add_event(
                GrowthEvent(
                    conversation_id=self.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.SUCCESS,
                    code=app.code,
                    stages=app.stages,
                    search_queries=app.search_queries or None,
                    search_results=app.search_results or None,
                    intent_suggestions=app.suggestions or None,
                )
            )

            return app

        except Exception as exc:
            await self._store.add_event(
                GrowthEvent(
                    conversation_id=self.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.ERROR,
                    error=str(exc),
                )
            )
            raise

    async def stream(self, intent: str, **opts: object) -> AsyncIterator[PipelineEvent]:
        """
        Stream generation or evolution with real LLM token streaming.

        Yields StageEvents, ChunkEvents (per token), and a final CompleteEvent.
        Automatically decides whether to generate or evolve based on conversation state.
        """
        model = str(opts.get("model", self.model))
        is_evolve = len(self._apps) > 0

        # Record user message
        await self._store.add_event(
            MessageEvent(conversation_id=self.id, role="user", content=intent)
        )

        settings = self.settings.model_copy()
        web_search = opts.get("web_search", settings.enable_web_search)
        if isinstance(web_search, bool):
            settings.enable_web_search = web_search

        try:
            if is_evolve:
                current = self.current_app
                assert current is not None
                gen = stream_evolve_pipeline(
                    new_intent=intent,
                    current_code=current.code,
                    original_intent=current.intent,
                    model=model,
                    llm=self._llm,
                    search=self._search,
                    settings=settings,
                    version=self.version + 1,
                    parent_version=current.version,
                )
            else:
                gen = stream_generate_pipeline(
                    intent=intent,
                    model=model,
                    llm=self._llm,
                    search=self._search if settings.enable_web_search else None,
                    settings=settings,
                    version=self.version + 1,
                )

            async for event in gen:
                # Intercept CompleteEvent to update state
                if isinstance(event, PipelineCompleteEvent):
                    self._apps.append(event.app)
                    # Record event in store
                    event_cls = GrowthEvent if is_evolve else GenerationEvent
                    await self._store.add_event(
                        event_cls(
                            conversation_id=self.id,
                            intent=intent,
                            model=model,
                            status=EventStatus.SUCCESS,
                            code=event.app.code,
                            stages=event.app.stages,
                            search_queries=event.app.search_queries or None,
                            search_results=event.app.search_results or None,
                            intent_suggestions=event.app.suggestions or None,
                        )
                    )
                    # Update title on first generation
                    if not is_evolve and self.version == 1:
                        title = intent[:80] + ("..." if len(intent) > 80 else "")
                        await self._store.update_conversation(self.id, title=title)

                yield event

        except Exception as exc:
            await self._store.add_event(
                (GrowthEvent if is_evolve else GenerationEvent)(
                    conversation_id=self.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.ERROR,
                    error=str(exc),
                )
            )
            yield PipelineErrorEvent(error=str(exc))
