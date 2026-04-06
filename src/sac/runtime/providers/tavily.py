"""
Tavily Search Provider

Default search provider using the Tavily API for AI-powered web search.
"""

from __future__ import annotations

import asyncio

import httpx

from sac.types import SearchResult, SearchSource

TAVILY_API_URL = "https://api.tavily.com/search"


class TavilyProvider:
    """Search provider backed by the Tavily API."""

    def __init__(
        self,
        api_key: str,
        *,
        search_depth: str = "basic",
        max_results: int = 3,
        include_images: bool = True,
    ) -> None:
        self._api_key = api_key
        self._search_depth = search_depth
        self._max_results = max_results
        self._include_images = include_images
        self._client = httpx.AsyncClient(timeout=30.0)

    async def search(self, queries: list[str], **kwargs: object) -> list[SearchResult]:
        """Execute multiple search queries in parallel and return results."""
        tasks = [self._search_single(q) for q in queries]
        return await asyncio.gather(*tasks)

    async def _search_single(self, query: str) -> SearchResult:
        """Execute a single search query."""
        response = await self._client.post(
            TAVILY_API_URL,
            json={
                "api_key": self._api_key,
                "query": query,
                "search_depth": self._search_depth,
                "max_results": self._max_results,
                "include_images": self._include_images,
                "include_raw_content": False,
            },
        )
        response.raise_for_status()
        data = response.json()

        return SearchResult(
            query=data.get("query", query),
            answer=data.get("answer"),
            sources=[
                SearchSource(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    content=r.get("content", ""),
                )
                for r in data.get("results", [])
            ],
            images=data.get("images"),
        )

    async def close(self) -> None:
        await self._client.aclose()
