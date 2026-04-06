"""
Streaming — observe pipeline stages in real time.

Usage:
    export SAC_API_KEY="sk-..."
    python examples/streaming.py
"""

import asyncio
import os

from sac import SaC


async def main():
    sac = SaC(api_key=os.environ["SAC_API_KEY"])
    conv = sac.conversation()

    async for event in conv.stream("travel guide for Hangzhou"):
        if event.type == "stage":
            print(f"Stage: {event.name} -> {event.status}")
        elif event.type == "chunk":
            print(event.data, end="")
        elif event.type == "complete":
            print(f"\n\nDone! Generated v{event.app.version} ({len(event.app.code)} chars)")
        elif event.type == "error":
            print(f"\nError: {event.error}")

    await sac.close()


if __name__ == "__main__":
    asyncio.run(main())
