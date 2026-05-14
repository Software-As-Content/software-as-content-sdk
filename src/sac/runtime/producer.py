"""
CodeProducer — the seam between SaC's protocol layer and code production.

SaC's core responsibility is conversation state, version chain, and the
generate/evolve state transitions. The actual "given an intent + optional
content + optional prior_app, produce a new App version" body is delegated
to a CodeProducer.

Pure rendering only. No search, no analyze, no agent-side concerns. Search
execution + suggestion generation live in `sac.agent` (or any external
agent driving core via /inbox).
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from sac.runtime.pipeline.evolve import evolve_pipeline, stream_evolve_pipeline
from sac.runtime.pipeline.generate import generate_pipeline, stream_generate_pipeline
from sac.runtime.providers.base import LLMProvider
from sac.types import App, ConversationSettings, PipelineEvent


class CodeProducer(Protocol):
    """Strategy that turns (intent, content?, prior_app?) into a new App version."""

    async def produce(
        self,
        intent: str,
        prior_app: App | None,
        settings: ConversationSettings,
        model: str,
        version: int,
        content: str | None = None,
    ) -> App: ...

    def stream(
        self,
        intent: str,
        prior_app: App | None,
        settings: ConversationSettings,
        model: str,
        version: int,
        content: str | None = None,
    ) -> AsyncIterator[PipelineEvent]: ...


class DefaultCodeProducer:
    """Default producer — wraps the core (search-free) generate/evolve pipelines."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def produce(
        self,
        intent: str,
        prior_app: App | None,
        settings: ConversationSettings,
        model: str,
        version: int,
        content: str | None = None,
    ) -> App:
        if prior_app is None:
            return await generate_pipeline(
                intent=intent,
                model=model,
                llm=self._llm,
                settings=settings,
                version=version,
                content=content,
            )
        return await evolve_pipeline(
            new_intent=intent,
            current_code=prior_app.code,
            original_intent=prior_app.intent,
            model=model,
            llm=self._llm,
            settings=settings,
            version=version,
            parent_version=prior_app.version,
            content=content,
        )

    def stream(
        self,
        intent: str,
        prior_app: App | None,
        settings: ConversationSettings,
        model: str,
        version: int,
        content: str | None = None,
    ) -> AsyncIterator[PipelineEvent]:
        if prior_app is None:
            return stream_generate_pipeline(
                intent=intent,
                model=model,
                llm=self._llm,
                settings=settings,
                version=version,
                content=content,
            )
        return stream_evolve_pipeline(
            new_intent=intent,
            current_code=prior_app.code,
            original_intent=prior_app.intent,
            model=model,
            llm=self._llm,
            settings=settings,
            version=version,
            parent_version=prior_app.version,
            content=content,
        )
