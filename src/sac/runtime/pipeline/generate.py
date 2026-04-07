"""
Generate Pipeline

Orchestrates the generation flow:
  analyze → search → generate (parallel with intent suggestions)

Ported from: src/app/api/generate-agentic/route.ts
"""

from __future__ import annotations

import asyncio
import json
import re

from sac.runtime.pipeline.events import PipelineEmitter
from sac.runtime.prompts.app import build_final_system_prompt, build_generation_prompt
from sac.runtime.prompts.intent import get_intent_suggestion_prompt, parse_intent_suggestions
from sac.runtime.prompts.search import build_search_context_prompt, get_search_query_extraction_prompt
from sac.runtime.providers.base import LLMProvider, SearchProvider
from typing import AsyncIterator

from sac.types import (
    App,
    ConversationSettings,
    IntentSuggestion,
    Message,
    PipelineChunkEvent,
    PipelineCompleteEvent,
    PipelineErrorEvent,
    PipelineEvent,
    PipelineStageEvent,
    SearchQuery,
    SearchResult,
    StageStatus,
)


async def generate_pipeline(
    intent: str,
    model: str,
    llm: LLMProvider,
    search: SearchProvider | None,
    settings: ConversationSettings,
    version: int = 1,
) -> App:
    """
    Run the full generation pipeline.

    If web search is enabled and a search provider is available:
      1. Extract search queries from user intent
      2. Execute web searches
      3. Generate UI with real data (parallel with intent suggestions)

    Otherwise: direct generation without search.
    """
    emitter = PipelineEmitter()

    system_prompt = build_final_system_prompt(
        custom_instructions=settings.custom_instructions,
        include_design_system=settings.use_design_system,
    )

    enable_search = settings.enable_web_search and search is not None
    search_queries: list[SearchQuery] = []
    search_results: list[SearchResult] = []
    suggestions: list[IntentSuggestion] = []

    if not enable_search:
        # Direct generation without search
        emitter.start("generate")
        try:
            prompt = build_generation_prompt(intent, system_prompt)
            content = await llm.complete(model, [Message(role="user", content=prompt)])
            emitter.complete("generate")
        except Exception:
            emitter.error("generate")
            raise

        code = _extract_code(content)
        return App(
            code=code,
            version=version,
            intent=intent,
            model=model,
            stages=emitter.stages,
        )

    # === AGENTIC FLOW WITH WEB SEARCH ===

    # Step 1: Extract search queries
    emitter.start("analyze")
    try:
        search_queries = await _extract_search_queries(intent, model, llm)
        emitter.complete("analyze")
    except Exception:
        emitter.error("analyze")
        raise

    # Step 2: Execute web searches
    if search_queries:
        emitter.start("search")
        try:
            query_strings = [q.query for q in search_queries]
            search_results = await search.search(query_strings)
            emitter.complete("search")
        except Exception:
            emitter.error("search")
            raise

    # Step 3: Generate UI with data (parallel with intent suggestions)
    emitter.start("generate")
    try:
        if search_results:
            generate_task = _generate_ui_with_data(intent, system_prompt, search_results, model, llm)
            suggest_task = _generate_intent_suggestions(
                intent, search_results, model, llm, settings.intent_rules
            )
            content, suggestions = await asyncio.gather(
                generate_task,
                suggest_task,
            )
        else:
            prompt = build_generation_prompt(intent, system_prompt)
            content = await llm.complete(model, [Message(role="user", content=prompt)])

        emitter.complete("generate")
    except Exception:
        emitter.error("generate")
        raise

    code = _extract_code(content)

    return App(
        code=code,
        version=version,
        intent=intent,
        model=model,
        search_queries=search_queries,
        search_results=search_results,
        suggestions=suggestions,
        stages=emitter.stages,
    )


async def stream_generate_pipeline(
    intent: str,
    model: str,
    llm: LLMProvider,
    search: SearchProvider | None,
    settings: ConversationSettings,
    version: int = 1,
) -> AsyncIterator[PipelineEvent]:
    """
    Streaming version of generate_pipeline.
    Yields PipelineEvents including ChunkEvents for each LLM token.
    """
    system_prompt = build_final_system_prompt(
        custom_instructions=settings.custom_instructions,
        include_design_system=settings.use_design_system,
    )

    enable_search = settings.enable_web_search and search is not None
    search_queries: list[SearchQuery] = []
    search_results: list[SearchResult] = []

    if enable_search:
        # Step 1: Extract search queries
        yield PipelineStageEvent(name="analyze", status=StageStatus.RUNNING)
        try:
            search_queries = await _extract_search_queries(intent, model, llm)
            yield PipelineStageEvent(name="analyze", status=StageStatus.COMPLETED)
        except Exception as exc:
            yield PipelineStageEvent(name="analyze", status=StageStatus.ERROR)
            yield PipelineErrorEvent(error=str(exc))
            return

        # Step 2: Execute web searches
        if search_queries:
            yield PipelineStageEvent(name="search", status=StageStatus.RUNNING)
            try:
                query_strings = [q.query for q in search_queries]
                search_results = await search.search(query_strings)
                yield PipelineStageEvent(name="search", status=StageStatus.COMPLETED)
            except Exception as exc:
                yield PipelineStageEvent(name="search", status=StageStatus.ERROR)
                yield PipelineErrorEvent(error=str(exc))
                return

    # Step 3: Stream code generation
    yield PipelineStageEvent(name="generate", status=StageStatus.RUNNING)

    # Start intent suggestions in parallel (non-blocking)
    suggest_task = asyncio.create_task(
        _generate_intent_suggestions(intent, search_results, model, llm, settings.intent_rules)
    )

    # Build prompt
    if search_results:
        search_context = build_search_context_prompt(search_results)
        prompt = f"{system_prompt}\n\n{search_context}\n\nUSER REQUEST: {intent}"
    else:
        prompt = build_generation_prompt(intent, system_prompt)

    # Stream LLM tokens
    full_content = ""
    try:
        async for token in llm.stream(model, [Message(role="user", content=prompt)]):
            full_content += token
            yield PipelineChunkEvent(data=token)
    except Exception as exc:
        yield PipelineStageEvent(name="generate", status=StageStatus.ERROR)
        yield PipelineErrorEvent(error=str(exc))
        suggest_task.cancel()
        return

    code = _extract_code(full_content)
    suggestions = await suggest_task

    yield PipelineStageEvent(name="generate", status=StageStatus.COMPLETED)
    yield PipelineCompleteEvent(app=App(
        code=code,
        version=version,
        intent=intent,
        model=model,
        search_queries=search_queries,
        search_results=search_results,
        suggestions=suggestions,
    ))


# ─── Internal helpers ──────────────────────────────────────────────


async def _extract_search_queries(intent: str, model: str, llm: LLMProvider) -> list[SearchQuery]:
    """Extract search queries from user intent via LLM."""
    search_prompt = get_search_query_extraction_prompt()
    response = await llm.complete(
        model,
        [
            Message(role="system", content=search_prompt),
            Message(role="user", content=intent),
        ],
    )

    try:
        json_str = response
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if match:
            json_str = match.group(1)
        parsed = json.loads(json_str.strip())
        return [SearchQuery(**q) for q in parsed.get("queries", [])]
    except (json.JSONDecodeError, KeyError, ValueError):
        return [SearchQuery(query=intent, purpose="main search")]


async def _generate_ui_with_data(
    intent: str,
    system_prompt: str,
    search_results: list[SearchResult],
    model: str,
    llm: LLMProvider,
) -> str:
    """Generate UI code with search context injected."""
    search_context = build_search_context_prompt(search_results)
    enhanced_prompt = f"{system_prompt}\n\n{search_context}\n\nUSER REQUEST: {intent}"
    return await llm.complete(model, [Message(role="user", content=enhanced_prompt)])


async def _generate_intent_suggestions(
    intent: str,
    search_results: list[SearchResult],
    model: str,
    llm: LLMProvider,
    custom_rules: str | None = None,
) -> list[IntentSuggestion]:
    """Generate intent suggestions (non-critical, returns empty on failure)."""
    try:
        prompt = get_intent_suggestion_prompt(intent, search_results, custom_rules)
        response = await llm.complete(model, [Message(role="user", content=prompt)])
        return parse_intent_suggestions(response)
    except Exception:
        return []


def _extract_code(content: str) -> str:
    """Extract code from LLM response, stripping markdown fences if present."""
    match = re.search(r"```(?:tsx|jsx)?\s*([\s\S]*?)```", content)
    if match:
        return match.group(1).strip()
    return content.strip()
