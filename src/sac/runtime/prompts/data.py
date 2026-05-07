"""
Data Context Prompt

The single way SaC's core renderer wraps "data to render". Whether the data
came from a web search, an upstream agent's task output, a database query, or
a hand-rolled JSON blob — once it's a string in front of the renderer, it
gets wrapped here.

This is the only data-context wrapper in core. The earlier separate wrappers
(`build_search_context_prompt` for search results, `build_content_context_prompt`
for agent-supplied content) were collapsed because the distinction was leaking
"how was this fetched" into the rendering layer — which, by SaC's content-
grounded rule, is not a rendering concern.
"""

from __future__ import annotations


def build_data_context_prompt(data: str) -> str:
    """Wrap a data string with rendering instructions for the LLM."""
    return f"""<data>
The following is the source data for this rendering. Use the actual values
present below; do not invent, fabricate, or web-search for additional facts.
Render what is provided. If the data contains URLs, sources, or images, you
may surface them as citations or visual elements.

{data}
</data>

DATA USAGE RULES:
1. Treat the block above as authoritative — display real values, not placeholders
2. Format numbers, dates, and structures faithfully
3. Surface source URLs/citations when present
4. Use any image URLs in the data via <img> tags to enhance visual richness
5. Do not introduce data that isn't present in the block"""
