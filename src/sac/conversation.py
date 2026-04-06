"""
Conversation — the core stateful primitive of SaC.

Each Conversation instance represents a single session where UI is generated and evolved.
"""

from __future__ import annotations

from typing import AsyncIterator

from sac.pipeline.evolve import evolve_pipeline
from sac.pipeline.generate import generate_pipeline
from sac.prompts.app import DEFAULT_MODEL
from sac.providers.base import LLMProvider, SearchProvider
from sac.store.base import ConversationStore
from sac.types import (
    App,
    ConversationData,
    ConversationSettings,
    EventStatus,
    GenerationEvent,
    GrowthEvent,
    MessageEvent,
    PipelineChunkEvent,
    PipelineCompleteEvent,
    PipelineErrorEvent,
    PipelineEvent,
    PipelineStageEvent,
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
        Stream generation or evolution, yielding stage/chunk/complete events.

        Automatically decides whether to generate or evolve based on conversation state.
        """
        is_evolve = len(self._apps) > 0

        # Yield initial stage
        yield PipelineStageEvent(name="analyze" if not is_evolve else "search", status=StageStatus.RUNNING)

        try:
            if is_evolve:
                app = await self.evolve(intent, **opts)
            else:
                app = await self.generate(intent, **opts)

            # Emit stage events from the pipeline
            for stage in app.stages:
                yield PipelineStageEvent(name=stage.name, status=stage.status)

            # Emit complete
            yield PipelineCompleteEvent(app=app)

        except Exception as exc:
            yield PipelineErrorEvent(error=str(exc))
