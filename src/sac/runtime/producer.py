"""
CodeProducer — the seam between SaC's protocol layer and code production.

SaC's core responsibility is conversation state, version chain, and the
generate/evolve state transitions. The actual "given an intent (and optional
prior app), produce a new App version" body is delegated to a CodeProducer.

This is what makes SaC's protocol shape stable while leaving room for the
production strategy to evolve (default LLM + search today, agent-loop tomorrow,
external agent system after that). Search is one tool the default producer
uses internally — it is not a fixed step of SaC's state machine.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from sac.runtime.pipeline.evolve import evolve_pipeline, stream_evolve_pipeline
from sac.runtime.pipeline.generate import generate_pipeline, stream_generate_pipeline
from sac.runtime.providers.base import LLMProvider, SearchProvider
from sac.types import App, ConversationSettings, PipelineEvent


class CodeProducer(Protocol):
    """Strategy that turns (intent, prior_app, settings) into a new App version.

    `content` (optional) is data supplied directly by an upstream agent. When
    present, the producer should treat it as already-resolved source material
    and avoid re-searching. The protocol layer does not interpret content; it
    just hands it through.
    """

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
    """
    Default producer — wraps the built-in generate/evolve pipelines.

    Uses an LLMProvider for code generation and an optional SearchProvider as
    a tool when the conversation's settings enable web search. Search is an
    internal implementation detail of this producer; SaC's protocol layer
    does not know it exists.
    """

    def __init__(self, llm: LLMProvider, search: SearchProvider | None) -> None:
        self._llm = llm
        self._search = search

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
                search=self._search if settings.enable_web_search else None,
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
            search=self._search,
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
                search=self._search if settings.enable_web_search else None,
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
            search=self._search,
            settings=settings,
            version=version,
            parent_version=prior_app.version,
            content=content,
        )
