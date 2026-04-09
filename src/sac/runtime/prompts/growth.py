"""
Growth Prompts

Handles the logic for growing an agentic app by integrating new data/intent.
Uses a single unified prompt that decides AND generates in one call.

Ported from: src/lib/growth-prompts.ts
"""

from __future__ import annotations

from sac.types import SearchResult

DEFAULT_GROWTH_RULES = """**EXTEND CURRENT PAGE** when:
- New data complements existing content (same domain/topic)
- Can be added as new section, component, or UI element
- Won't clutter or confuse the current layout

**ADD NEW PAGE** when:
- New data represents a fundamentally different topic
- Would require completely different UI structure
- Deserves its own dedicated view
- If adding a new page, also add navigation (tabs, menu, etc.) to switch between pages"""


def _format_search_results(search_results: list[SearchResult]) -> str:
    """Format search results for context."""
    if not search_results:
        return "No search data available"

    sections: list[str] = []
    for result in search_results:
        sources = "\n".join(
            f"- {s.title}: {s.content[:200]}..."
            for s in result.sources[:3]
        )
        section = f'Query: "{result.query}"'
        if result.answer:
            section += f"\nSummary: {result.answer}"
        section += f"\nSources:\n{sources}"
        sections.append(section)

    return "\n\n".join(sections)


def build_growth_prompt(
    current_code: str,
    original_intent: str,
    new_intent: str,
    search_results: list[SearchResult],
    system_prompt: str,
    custom_growth_rules: str | None = None,
) -> str:
    """
    Build a unified prompt that decides growth type AND generates updated code in one call.
    This reduces latency by eliminating the separate decision step.
    """
    search_context = _format_search_results(search_results)
    growth_rules = (custom_growth_rules or "").strip() or DEFAULT_GROWTH_RULES

    return f"""{system_prompt}

You are growing an existing agentic app based on a new user intent and new data.

=== CURRENT APP ===
Original Intent: {original_intent}

Current Code:
```tsx
{current_code}
```

=== NEW REQUEST ===
New Intent: {new_intent}

New Data Retrieved:
{search_context}

=== GROWTH RULES ===
Decide how to integrate the new content:

{growth_rules}

=== OUTPUT REQUIREMENTS ===
1. First, output a JSON block with your decision:
```json
{{
  "growthType": "extend_current" | "new_page",
  "reason": "Brief explanation",
  "changes": "User-facing summary of what changed (same language as user intent)"
}}
```

2. Then output the complete updated React component code:
```tsx
// Your complete updated code here
```

IMPORTANT:
- Keep ALL existing functionality intact
- Integrate the new data naturally
- Maintain consistent styling
- Output BOTH the JSON decision AND the complete code
- Add a small "NEW" badge (e.g. <Badge>NEW</Badge>) next to newly added tabs, sections, or major content blocks so the user can instantly spot what's new. Remove any such badges from previously existing content."""
