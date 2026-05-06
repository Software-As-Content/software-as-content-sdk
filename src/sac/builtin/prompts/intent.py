"""
Intent Suggestion Prompts

Generates contextual intent suggestions based on user's original intent
and the data retrieved from web searches.

Ported from: src/lib/intent-prompts.ts
"""

from __future__ import annotations

import json
import re

from sac.types import IntentSuggestion, IntentType, SearchResult

DEFAULT_INTENT_RULES = """1. Suggestions should be EXTENSIONS of the user's original intent, building on what they've already done
2. Each suggestion should leverage or expand on the DATA that was searched
3. Do NOT suggest generic UI changes like "dark mode", "mobile view", "add filters" - these are system features
4. Focus on domain-specific actions that add VALUE to the user's task
5. Be concise - labels should be 2-4 words max"""


def get_intent_suggestion_prompt(
    user_intent: str,
    search_results: list[SearchResult],
    custom_rules: str | None = None,
) -> str:
    """Build the prompt for generating intent suggestions."""
    # Format search results for context
    search_context_parts: list[str] = []
    for result in search_results:
        sources = "\n".join(
            f"- {s.title}: {s.content[:200]}..."
            for s in result.sources[:2]
        )
        part = f'Query: "{result.query}"'
        if result.answer:
            part += f"\nSummary: {result.answer}"
        part += f"\nSources:\n{sources}"
        search_context_parts.append(part)

    search_context = "\n\n".join(search_context_parts) or "No search data available"
    rules = (custom_rules or "").strip() or DEFAULT_INTENT_RULES

    return f"""You are an AI assistant that generates contextual follow-up intent suggestions based on the user's original intent and the data retrieved from web searches.

Given a user's original intent and the data retrieved from web searches, suggest 2-3 natural follow-up actions that would help the user advance their intent or task.

IMPORTANT RULES:
{rules}

USER'S ORIGINAL INTENT:
{user_intent}

RETRIEVED DATA:
{search_context}

OUTPUT FORMAT (JSON only, no explanation):
{{
  "suggestions": [
    {{ "label": "Short Label", "prompt": "Full prompt that extends the original intent with this action", "type": "action|explore|refine|enhance" }}
  ]
}}

Generate 2-3 highly relevant, contextual suggestions:"""


def parse_intent_suggestions(response: str) -> list[IntentSuggestion]:
    """Parse the LLM response into IntentSuggestion list."""
    try:
        json_str = response
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if match:
            json_str = match.group(1)

        parsed = json.loads(json_str.strip())

        if not isinstance(parsed.get("suggestions"), list):
            return []

        valid_types = {"action", "explore", "refine", "enhance"}
        suggestions: list[IntentSuggestion] = []

        for s in parsed["suggestions"][:3]:
            prompt = s.get("prompt", "")
            if not prompt:
                continue
            raw_type = s.get("type", "action")
            intent_type = IntentType(raw_type) if raw_type in valid_types else IntentType.ACTION
            suggestions.append(
                IntentSuggestion(
                    label=s.get("label", "Suggestion"),
                    prompt=prompt,
                    type=intent_type,
                )
            )

        return suggestions

    except (json.JSONDecodeError, KeyError, ValueError):
        return []
