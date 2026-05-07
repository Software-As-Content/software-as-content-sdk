"""
Growth Prompt

Builds the unified prompt that decides growth type AND emits new code in one
LLM call. Receives data via the `content` parameter (caller-provided string);
core renderer is content-shape-agnostic.
"""

from __future__ import annotations

DEFAULT_GROWTH_RULES = """**EXTEND CURRENT PAGE** when:
- New data complements existing content (same domain/topic)
- Can be added as new section, component, or UI element
- Won't clutter or confuse the current layout

**ADD NEW PAGE** when:
- New data represents a fundamentally different topic
- Would require completely different UI structure
- Deserves its own dedicated view
- If adding a new page, also add navigation (tabs, menu, etc.) to switch between pages"""


def build_growth_prompt(
    current_code: str,
    original_intent: str,
    new_intent: str,
    system_prompt: str,
    custom_growth_rules: str | None = None,
    content: str | None = None,
) -> str:
    """Unified prompt: decide growth type AND emit new code."""
    new_data_section = content.strip() if content else "No new data provided"
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

New Data:
{new_data_section}

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
