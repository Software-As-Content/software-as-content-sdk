"""
Evolve Pipeline

Orchestrates the evolution/growth flow:
  search → unified growth (decision + code) (parallel with intent suggestions)

Ported from: src/app/api/grow-app/route.ts
"""

from __future__ import annotations

import asyncio
import json
import re

from sac.pipeline.events import PipelineEmitter
from sac.prompts.app import build_final_system_prompt
from sac.prompts.growth import build_growth_prompt
from sac.prompts.intent import get_intent_suggestion_prompt, parse_intent_suggestions
from sac.prompts.search import get_search_query_extraction_prompt
from sac.providers.base import LLMProvider, SearchProvider
from sac.types import (
    App,
    ConversationSettings,
    GrowthDecision,
    GrowthType,
    IntentSuggestion,
    Message,
    SearchQuery,
    SearchResult,
)


async def evolve_pipeline(
    new_intent: str,
    current_code: str,
    original_intent: str,
    model: str,
    llm: LLMProvider,
    search: SearchProvider | None,
    settings: ConversationSettings,
    version: int = 2,
    parent_version: int = 1,
) -> App:
    """
    Run the evolution pipeline.

    1. Extract search queries from new intent
    2. Execute searches
    3. Unified growth prompt (decision + code generation in single LLM call)
    4. Parallel intent suggestion generation
    """
    emitter = PipelineEmitter()

    system_prompt = build_final_system_prompt(
        custom_instructions=settings.custom_instructions,
        include_design_system=settings.use_design_system,
    )

    search_queries: list[SearchQuery] = []
    search_results: list[SearchResult] = []
    suggestions: list[IntentSuggestion] = []

    # Step 1: Search for new data
    emitter.start("search")
    try:
        if search is not None:
            search_queries = await _extract_search_queries(new_intent, model, llm)
            if search_queries:
                query_strings = [q.query for q in search_queries]
                search_results = await search.search(query_strings)
        emitter.complete("search")
    except Exception:
        emitter.error("search")
        # Search failure is non-fatal for evolve — continue with empty results

    # Step 2: Unified growth — decide AND generate in one call
    emitter.start("generate")
    try:
        growth_prompt = build_growth_prompt(
            current_code=current_code,
            original_intent=original_intent,
            new_intent=new_intent,
            search_results=search_results,
            system_prompt=system_prompt,
            custom_growth_rules=settings.growth_rules or None,
        )

        # Start intent suggestions in parallel
        suggest_task = _generate_intent_suggestions(
            new_intent, search_results, model, llm, settings.intent_rules
        )

        # Single LLM call for decision + code generation
        response = await llm.complete(model, [Message(role="user", content=growth_prompt)])

        # Parse unified response
        decision, code = _parse_growth_response(response)

        # Wait for suggestions
        suggestions = await suggest_task

        emitter.complete("generate")
    except Exception:
        emitter.error("generate")
        raise

    return App(
        code=code,
        version=version,
        intent=new_intent,
        parent_version=parent_version,
        model=model,
        search_queries=search_queries,
        search_results=search_results,
        suggestions=suggestions,
        growth_decision=decision,
        stages=emitter.stages,
    )


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


def _parse_growth_response(response: str) -> tuple[GrowthDecision, str]:
    """Parse unified growth response containing decision + code."""
    # Extract JSON decision block
    decision = GrowthDecision(growth_type=GrowthType.EXTEND_CURRENT, reason="Default to extend")

    json_match = re.search(r"```json\s*([\s\S]*?)```", response)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1).strip())
            growth_type = parsed.get("growthType", "extend_current")
            if growth_type in ("extend_current", "new_page"):
                decision = GrowthDecision(
                    growth_type=GrowthType(growth_type),
                    reason=parsed.get("reason", "No reason provided"),
                )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Extract TSX code block
    code_match = re.search(r"```tsx\s*([\s\S]*?)```", response)
    code = code_match.group(1).strip() if code_match else response.strip()

    return decision, code


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
