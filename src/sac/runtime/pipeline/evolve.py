"""
Evolve Pipeline (core)

Pure rendering for version N+1. Takes prior code + new intent + optional
content (data already gathered by whoever called us) and produces a unified
LLM call that decides growth_type AND emits new code in one pass.

No search, no analyze, no intent suggestions — agent-layer concerns live
in `sac.builtin` (or any external agent driving core via /inbox).
"""

from __future__ import annotations

import json
import re
from typing import AsyncIterator

from sac.runtime.pipeline._tsx_filter import TsxChunkFilter
from sac.runtime.pipeline.events import PipelineEmitter
from sac.runtime.prompts.app import build_final_system_prompt
from sac.runtime.prompts.growth import build_growth_prompt
from sac.runtime.providers.base import LLMProvider
from sac.types import (
    App,
    ConversationSettings,
    GrowthDecision,
    GrowthType,
    Message,
    PipelineChunkEvent,
    PipelineCompleteEvent,
    PipelineErrorEvent,
    PipelineEvent,
    PipelineStageEvent,
    StageStatus,
)


async def evolve_pipeline(
    new_intent: str,
    current_code: str,
    original_intent: str,
    model: str,
    llm: LLMProvider,
    settings: ConversationSettings,
    version: int = 2,
    parent_version: int = 1,
    content: str | None = None,
) -> App:
    """Render the next App version. content (if present) is the new data."""
    emitter = PipelineEmitter()

    system_prompt = build_final_system_prompt(
        custom_instructions=settings.custom_instructions,
        include_design_system=settings.use_design_system,
    )

    emitter.start("generate")
    try:
        growth_prompt = build_growth_prompt(
            current_code=current_code,
            original_intent=original_intent,
            new_intent=new_intent,
            system_prompt=system_prompt,
            custom_growth_rules=settings.growth_rules or None,
            content=content,
        )
        response = await llm.complete(model, [Message(role="user", content=growth_prompt)])
        decision, code = _parse_growth_response(response)
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
        growth_decision=decision,
        stages=emitter.stages,
    )


async def stream_evolve_pipeline(
    new_intent: str,
    current_code: str,
    original_intent: str,
    model: str,
    llm: LLMProvider,
    settings: ConversationSettings,
    version: int = 2,
    parent_version: int = 1,
    content: str | None = None,
) -> AsyncIterator[PipelineEvent]:
    """Streaming variant of evolve_pipeline."""
    system_prompt = build_final_system_prompt(
        custom_instructions=settings.custom_instructions,
        include_design_system=settings.use_design_system,
    )

    yield PipelineStageEvent(name="generate", status=StageStatus.RUNNING)

    growth_prompt = build_growth_prompt(
        current_code=current_code,
        original_intent=original_intent,
        new_intent=new_intent,
        system_prompt=system_prompt,
        custom_growth_rules=settings.growth_rules or None,
        content=content,
    )

    # Stream LLM tokens through TsxChunkFilter so the frontend only sees TSX
    # body, not the JSON decision envelope. `full_content` accumulates the raw
    # response so `_parse_growth_response` can extract the JSON below.
    full_content = ""
    tsx_filter = TsxChunkFilter()
    try:
        async for token in llm.stream(model, [Message(role="user", content=growth_prompt)]):
            full_content += token
            for chunk in tsx_filter.feed(token):
                yield PipelineChunkEvent(data=chunk)
        for chunk in tsx_filter.finalize():
            yield PipelineChunkEvent(data=chunk)
    except Exception as exc:
        yield PipelineStageEvent(name="generate", status=StageStatus.ERROR)
        yield PipelineErrorEvent(error=str(exc))
        return

    decision, code = _parse_growth_response(full_content)

    yield PipelineStageEvent(name="generate", status=StageStatus.COMPLETED)
    yield PipelineCompleteEvent(app=App(
        code=code,
        version=version,
        intent=new_intent,
        parent_version=parent_version,
        model=model,
        growth_decision=decision,
    ))


# ─── Internal helpers ──────────────────────────────────────────────


def _parse_growth_response(response: str) -> tuple[GrowthDecision, str]:
    """Parse unified growth response containing decision + code."""
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
                    changes=parsed.get("changes", ""),
                )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    code_match = re.search(r"```tsx\s*([\s\S]*?)```", response)
    code = code_match.group(1).strip() if code_match else response.strip()

    return decision, code
