"""
BundledAgent — the default agent that ships with SaC.

Sibling-level to external agent systems (OpenClaw, LangGraph, ...). Owns:
  - search execution (extract queries → call SearchProvider → format results)
  - intent suggestion generation
  - classify chat-vs-update (for the standalone web UI's text input flow)
  - event recording around generate/evolve flows

Calls into core via `Conversation.ingest(content, intent)` for the actual
rendering. Search results, when present, are formatted into a content string
and passed via the same content path that any external agent would use —
there is no privileged in-process API.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator, TYPE_CHECKING

from sac.builtin.prompts.classify import CLASSIFY_COLD, CLASSIFY_WITH_CONTEXT
from sac.builtin.prompts.intent import (
    get_intent_suggestion_prompt,
    parse_intent_suggestions,
)
from sac.builtin.prompts.search import get_search_query_extraction_prompt
from sac.runtime.providers.base import LLMProvider, SearchProvider
from sac.types import (
    App,
    EventStatus,
    GenerationEvent,
    GrowthEvent,
    IntentSuggestion,
    Message,
    MessageEvent,
    PipelineCompleteEvent,
    PipelineErrorEvent,
    PipelineEvent,
    PipelineSearchEvent,
    PipelineStageEvent,
    SearchQuery,
    SearchResult,
    SendResult,
    SendResultType,
    StageStatus,
)

if TYPE_CHECKING:
    from sac.conversation import Conversation


class BundledAgent:
    """The default agent. One per SaC instance; shared across conversations."""

    def __init__(self, llm: LLMProvider, search: SearchProvider | None) -> None:
        self._llm = llm
        self._search = search

    # ─── Public methods (mirror of legacy Conversation API) ──────────

    async def generate(self, conv: "Conversation", intent: str, **opts: Any) -> App:
        model = str(opts.get("model", conv.model))
        web_search_opt = opts.get("web_search", conv.settings.enable_web_search)
        content_override = opts.get("content")
        content_override = content_override if isinstance(content_override, str) else None

        await conv._store.add_event(
            MessageEvent(conversation_id=conv.id, role="user", content=intent)
        )

        # Agent-supplied content path: skip search + suggestions entirely.
        if content_override is not None:
            try:
                app = await conv.ingest(content=content_override, intent=intent, model=model)
                await conv._store.add_event(
                    GenerationEvent(
                        conversation_id=conv.id,
                        intent=intent,
                        model=model,
                        status=EventStatus.SUCCESS,
                        code=app.code,
                        stages=app.stages,
                    )
                )
                if conv.version == 1:
                    title = intent[:80] + ("..." if len(intent) > 80 else "")
                    await conv._store.update_conversation(conv.id, title=title)
                return app
            except Exception as exc:
                await conv._store.add_event(
                    GenerationEvent(
                        conversation_id=conv.id,
                        intent=intent,
                        model=model,
                        status=EventStatus.ERROR,
                        error=str(exc),
                    )
                )
                raise

        # Standalone agentic flow: search (if enabled) + suggestions
        enable_search = bool(web_search_opt) and self._search is not None

        search_queries: list[SearchQuery] = []
        search_results: list[SearchResult] = []
        composed_content: str | None = None

        if enable_search:
            try:
                search_queries = await _extract_search_queries(intent, model, self._llm)
                if search_queries:
                    qs = [q.query for q in search_queries]
                    search_results = await self._search.search(qs)  # type: ignore[union-attr]
                    composed_content = _format_search_results_as_data(search_results)
            except Exception:
                # Search failure is non-fatal; carry on without data
                search_queries, search_results, composed_content = [], [], None

        try:
            app = await conv.ingest(content=composed_content, intent=intent, model=model)

            suggestions = await _generate_intent_suggestions(
                intent, search_results, model, self._llm, conv.settings.intent_rules
            )

            # Attach agent-side artefacts to the App (these are agent outputs,
            # not core renderer outputs, but the public App shape carries them).
            app.search_queries = search_queries
            app.search_results = search_results
            app.suggestions = suggestions

            await conv._store.add_event(
                GenerationEvent(
                    conversation_id=conv.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.SUCCESS,
                    code=app.code,
                    stages=app.stages,
                    search_queries=search_queries or None,
                    search_results=search_results or None,
                    intent_suggestions=suggestions or None,
                )
            )

            if conv.version == 1:
                title = intent[:80] + ("..." if len(intent) > 80 else "")
                await conv._store.update_conversation(conv.id, title=title)

            return app
        except Exception as exc:
            await conv._store.add_event(
                GenerationEvent(
                    conversation_id=conv.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.ERROR,
                    error=str(exc),
                )
            )
            raise

    async def evolve(self, conv: "Conversation", intent: str, **opts: Any) -> App:
        if conv.current_app is None:
            raise ValueError("No app to evolve. Call generate() first.")

        model = str(opts.get("model", conv.model))
        content_override = opts.get("content")
        content_override = content_override if isinstance(content_override, str) else None

        await conv._store.add_event(
            MessageEvent(conversation_id=conv.id, role="user", content=intent)
        )

        # Agent-supplied content path
        if content_override is not None:
            try:
                app = await conv.ingest(content=content_override, intent=intent, model=model)
                await conv._store.add_event(
                    GrowthEvent(
                        conversation_id=conv.id,
                        intent=intent,
                        model=model,
                        status=EventStatus.SUCCESS,
                        code=app.code,
                        stages=app.stages,
                    )
                )
                return app
            except Exception as exc:
                await conv._store.add_event(
                    GrowthEvent(
                        conversation_id=conv.id,
                        intent=intent,
                        model=model,
                        status=EventStatus.ERROR,
                        error=str(exc),
                    )
                )
                raise

        # Standalone agentic flow
        search_queries: list[SearchQuery] = []
        search_results: list[SearchResult] = []
        composed_content: str | None = None

        if self._search is not None:
            try:
                search_queries = await _extract_search_queries(intent, model, self._llm)
                if search_queries:
                    qs = [q.query for q in search_queries]
                    search_results = await self._search.search(qs)
                    composed_content = _format_search_results_as_data(search_results)
            except Exception:
                # Search failure is non-fatal for evolve — continue without data
                search_queries, search_results, composed_content = [], [], None

        try:
            app = await conv.ingest(content=composed_content, intent=intent, model=model)

            suggestions = await _generate_intent_suggestions(
                intent, search_results, model, self._llm, conv.settings.intent_rules
            )

            app.search_queries = search_queries
            app.search_results = search_results
            app.suggestions = suggestions

            await conv._store.add_event(
                GrowthEvent(
                    conversation_id=conv.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.SUCCESS,
                    code=app.code,
                    stages=app.stages,
                    search_queries=search_queries or None,
                    search_results=search_results or None,
                    intent_suggestions=suggestions or None,
                )
            )

            return app
        except Exception as exc:
            await conv._store.add_event(
                GrowthEvent(
                    conversation_id=conv.id,
                    intent=intent,
                    model=model,
                    status=EventStatus.ERROR,
                    error=str(exc),
                )
            )
            raise

    async def stream(
        self, conv: "Conversation", intent: str, **opts: Any
    ) -> AsyncIterator[PipelineEvent]:
        """Streaming variant. Yields stage/chunk/complete events."""
        model = str(opts.get("model", conv.model))
        is_evolve = conv.current_app is not None
        content_override = opts.get("content")
        content_override = content_override if isinstance(content_override, str) else None
        web_search_opt = opts.get("web_search", conv.settings.enable_web_search)

        await conv._store.add_event(
            MessageEvent(conversation_id=conv.id, role="user", content=intent)
        )

        search_queries: list[SearchQuery] = []
        search_results: list[SearchResult] = []
        composed_content: str | None = content_override
        run_search = (
            content_override is None
            and self._search is not None
            and (is_evolve or bool(web_search_opt))
        )

        if run_search:
            # Emit analyze stage (only the non-evolve path historically did this;
            # evolve historically had only a "search" stage). Keep that asymmetry
            # to match prior behavior.
            if not is_evolve:
                yield PipelineStageEvent(name="analyze", status=StageStatus.RUNNING)
                try:
                    search_queries = await _extract_search_queries(intent, model, self._llm)
                    yield PipelineStageEvent(name="analyze", status=StageStatus.COMPLETED)
                except Exception as exc:
                    yield PipelineStageEvent(name="analyze", status=StageStatus.ERROR)
                    yield PipelineErrorEvent(error=str(exc))
                    await self._record_error_event(conv, is_evolve, intent, model, str(exc))
                    return
            else:
                yield PipelineStageEvent(name="search", status=StageStatus.RUNNING)
                try:
                    search_queries = await _extract_search_queries(intent, model, self._llm)
                except Exception:
                    pass  # Non-fatal for evolve

            if search_queries:
                if not is_evolve:
                    yield PipelineStageEvent(name="search", status=StageStatus.RUNNING)
                try:
                    qs = [q.query for q in search_queries]
                    search_results = await self._search.search(qs)  # type: ignore[union-attr]
                    yield PipelineStageEvent(name="search", status=StageStatus.COMPLETED)
                    if search_results:
                        yield PipelineSearchEvent(queries=search_queries, results=search_results)
                except Exception as exc:
                    yield PipelineStageEvent(name="search", status=StageStatus.ERROR)
                    if not is_evolve:
                        yield PipelineErrorEvent(error=str(exc))
                        await self._record_error_event(conv, is_evolve, intent, model, str(exc))
                        return
                    # evolve: non-fatal; continue
            elif is_evolve:
                yield PipelineStageEvent(name="search", status=StageStatus.COMPLETED)

            if search_results:
                composed_content = _format_search_results_as_data(search_results)

        # Suggestions in parallel with code generation
        suggest_task = asyncio.create_task(
            _generate_intent_suggestions(
                intent, search_results, model, self._llm, conv.settings.intent_rules
            )
        )

        # Forward core's stream events
        try:
            async for event in conv.stream_ingest(content=composed_content, intent=intent, model=model):
                if isinstance(event, PipelineCompleteEvent):
                    suggestions = await suggest_task
                    event.app.search_queries = search_queries
                    event.app.search_results = search_results
                    event.app.suggestions = suggestions

                    event_cls = GrowthEvent if is_evolve else GenerationEvent
                    await conv._store.add_event(
                        event_cls(
                            conversation_id=conv.id,
                            intent=intent,
                            model=model,
                            status=EventStatus.SUCCESS,
                            code=event.app.code,
                            stages=event.app.stages,
                            search_queries=search_queries or None,
                            search_results=search_results or None,
                            intent_suggestions=suggestions or None,
                        )
                    )
                    if not is_evolve and conv.version == 1:
                        title = intent[:80] + ("..." if len(intent) > 80 else "")
                        await conv._store.update_conversation(conv.id, title=title)

                yield event
        except Exception as exc:
            suggest_task.cancel()
            await self._record_error_event(conv, is_evolve, intent, model, str(exc))
            yield PipelineErrorEvent(error=str(exc))

    async def send(self, conv: "Conversation", message: str, **opts: Any) -> SendResult:
        """Unified entry — classify chat vs update, then dispatch."""
        classification = await self.classify(conv, message)

        if classification["type"] == "chat":
            reply = classification.get("reply", "")
            await conv._store.add_event(
                MessageEvent(conversation_id=conv.id, role="user", content=message)
            )
            await conv._store.add_event(
                MessageEvent(conversation_id=conv.id, role="assistant", content=reply)
            )
            return SendResult(type=SendResultType.CHAT, reply=reply)

        if conv.current_app is not None:
            app = await self.evolve(conv, message, **opts)
            return SendResult(type=SendResultType.EVOLVE, app=app)
        else:
            app = await self.generate(conv, message, **opts)
            return SendResult(type=SendResultType.GENERATE, app=app)

    async def classify(self, conv: "Conversation", message: str) -> dict:
        """Classify a user message as 'chat' or 'update' via LLM."""
        has_context = conv.current_app is not None
        system_prompt = CLASSIFY_WITH_CONTEXT if has_context else CLASSIFY_COLD

        user_content = message
        if has_context and conv.current_app:
            user_content = (
                f"[Current app intent: {conv.current_app.intent}]\n\nUser message: {message}"
            )

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

        try:
            raw = await self._llm.complete(conv.model, messages, max_tokens=256)
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
            return {"type": "update"}

    # ─── Helpers ──────────────────────────────────────────────────────

    async def _record_error_event(
        self,
        conv: "Conversation",
        is_evolve: bool,
        intent: str,
        model: str,
        error: str,
    ) -> None:
        event_cls = GrowthEvent if is_evolve else GenerationEvent
        await conv._store.add_event(
            event_cls(
                conversation_id=conv.id,
                intent=intent,
                model=model,
                status=EventStatus.ERROR,
                error=error,
            )
        )


# ─── Module-level helpers (no class state needed) ──────────────────


async def _extract_search_queries(
    intent: str, model: str, llm: LLMProvider
) -> list[SearchQuery]:
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


def _format_search_results_as_data(search_results: list[SearchResult]) -> str:
    """Format search results into a content string for the renderer's data context.

    Mirrors the rich source/image format previously inlined in
    `build_search_context_prompt`, minus the wrapper. The renderer's unified
    `build_data_context_prompt` will wrap this once, with generic instructions.
    """
    sections: list[str] = []
    for result in search_results:
        sources = "\n\n".join(
            f"  {i + 1}. {s.title}\n     {s.content}"
            for i, s in enumerate(result.sources)
        )
        images_section = ""
        if result.images:
            images_section = (
                f"\nImages ({len(result.images)} available):\n"
                + "\n".join(f"  {i + 1}. {img}" for i, img in enumerate(result.images))
            )
        section = f'### Search: "{result.query}"'
        if result.answer:
            section += f"\nSummary: {result.answer}\n"
        section += f"\nSources:\n{sources}{images_section}"
        sections.append(section)
    return "\n\n---\n\n".join(sections)
