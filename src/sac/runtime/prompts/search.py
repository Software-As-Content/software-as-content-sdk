"""
Search-Related Prompts

Prompts for extracting search queries and generating UI with real data.

Ported from: src/lib/search-prompts.ts
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sac.types import SearchResult


def _get_current_date_info() -> dict[str, object]:
    """Get the current date formatted for prompts."""
    now = datetime.now(timezone.utc)
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    return {
        "year": now.year,
        "month": months[now.month - 1],
        "month_num": now.month,
        "day": now.day,
        "full_date": f"{months[now.month - 1]} {now.day}, {now.year}",
    }


def get_search_query_extraction_prompt() -> str:
    """Build the search query extraction prompt with current date."""
    date = _get_current_date_info()

    return f"""You are an expert at understanding user requests and determining what information needs to be searched on the web.

CURRENT DATE: {date['full_date']}
CURRENT YEAR: {date['year']}

Given a user's request for a UI component, analyze what real-world data would be needed and generate appropriate search queries.

RULES:
1. Generate 1-5 search queries that would retrieve the most relevant real-time data
2. Each query should be specific and focused on retrieving factual, up-to-date information
3. IMPORTANT: Include the current year ({date['year']}) in queries when searching for recent/current information
4. Consider what data the UI would display and search for that specific information
5. Output ONLY valid JSON, no explanations

OUTPUT FORMAT:
{{
  "queries": [
    {{ "query": "search query here", "purpose": "what this data will be used for in the UI" }}
  ]
}}

EXAMPLES:

User: "Create a dashboard showing Tesla stock performance"
Output:
{{
  "queries": [
    {{ "query": "Tesla TSLA stock price today {date['year']}", "purpose": "current stock price and daily change" }},
    {{ "query": "Tesla stock performance last 6 months {date['year']}", "purpose": "historical data for charts" }},
    {{ "query": "Tesla latest news {date['month']} {date['year']}", "purpose": "recent news and events" }}
  ]
}}

User: "Build a weather widget for San Francisco"
Output:
{{
  "queries": [
    {{ "query": "San Francisco weather today forecast", "purpose": "current weather conditions" }},
    {{ "query": "San Francisco 7 day weather forecast", "purpose": "weekly forecast data" }}
  ]
}}

User: "Show me a comparison of iPhone 16 vs Samsung S25"
Output:
{{
  "queries": [
    {{ "query": "iPhone 16 specifications price {date['year']}", "purpose": "iPhone specs and pricing" }},
    {{ "query": "Samsung Galaxy S25 specifications price {date['year']}", "purpose": "Samsung specs and pricing" }},
    {{ "query": "iPhone 16 vs Samsung S25 comparison review {date['year']}", "purpose": "comparison insights" }}
  ]
}}"""


def build_search_context_prompt(search_results: list[SearchResult]) -> str:
    """Build the prompt for UI generation with search context."""
    sections: list[str] = []

    for result in search_results:
        sources = "\n\n".join(
            f"  {i + 1}. {s.title}\n     {s.content}"
            for i, s in enumerate(result.sources)
        )

        images_section = ""
        if result.images:
            images_section = f"\nImages ({len(result.images)} available):\n" + "\n".join(
                f"  {i + 1}. {img}" for i, img in enumerate(result.images)
            )

        section = f'### Search: "{result.query}"'
        if result.answer:
            section += f"\nSummary: {result.answer}\n"
        section += f"\nSources:\n{sources}{images_section}"
        sections.append(section)

    formatted = "\n\n---\n\n".join(sections)

    return f"""<real-time-data>
The following is real-time data retrieved from the web. Use this ACTUAL data to populate the UI.
Do NOT use placeholder or mock data - use the real information provided below.

{formatted}
</real-time-data>

IMPORTANT DATA USAGE RULES:
1. Extract actual numbers, names, prices, dates from the search results above
2. Display real data in the UI - not "Loading..." or "$XX.XX" placeholders
3. If specific data isn't available, use reasonable values based on context, but prefer real data
4. Include source attribution where appropriate (e.g., "Data from..." or small source links)
5. Format numbers and dates appropriately for display
6. USE THE PROVIDED IMAGES: When images are available in the search results, incorporate them into the UI using <img> tags with the provided URLs. Use images to enhance visual appeal and provide context. Include multiple images when feasible to create a richer, more informative UI."""


def should_enable_search(user_intent: str) -> bool:
    """Determine if a user intent likely needs web search."""
    patterns = [
        # Real-time data indicators
        r"\b(current|today|now|latest|recent|live|real-time)\b",
        r"\b(stock|price|weather|news|score|rate|crypto)\b",
        r"\b(compare|comparison|vs|versus)\b",
        # Specific entities that would need lookup
        r"\b(tesla|apple|google|amazon|microsoft|bitcoin|ethereum)\b",
        r"\b(iphone|samsung|pixel|macbook)\b",
        # Location-based
        r"\b(in|for|of)\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?\b",
    ]
    return any(re.search(p, user_intent, re.IGNORECASE) for p in patterns)
