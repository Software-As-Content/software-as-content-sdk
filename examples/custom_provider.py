"""
Custom Provider — bring your own LLM backend.

This example shows how to implement a custom LLM provider
that works with any API (Anthropic, OpenAI direct, local models, etc.)

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python examples/custom_provider.py
"""

import asyncio
import os
from typing import AsyncIterator

import httpx

from sac import SaC
from sac.types import Message


class AnthropicProvider:
    """Example: direct Anthropic API provider."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(self, model: str, messages: list[Message], **kwargs: object) -> str:
        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 8192,
                "messages": [{"role": m.role, "content": m.content} for m in messages if m.role != "system"],
                "system": next((m.content for m in messages if m.role == "system"), ""),
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]

    async def stream(self, model: str, messages: list[Message], **kwargs: object) -> AsyncIterator[str]:
        # Simplified — real implementation would use SSE streaming
        content = await self.complete(model, messages, **kwargs)
        yield content

    async def close(self) -> None:
        await self._client.aclose()


async def main():
    sac = SaC(
        llm=AnthropicProvider(os.environ["ANTHROPIC_API_KEY"]),
        model="claude-sonnet-4-5-20250514",
    )

    app = await sac.generate("a simple todo app")
    print(app.code)
    await sac.close()


if __name__ == "__main__":
    asyncio.run(main())
