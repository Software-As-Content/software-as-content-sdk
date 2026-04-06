"""
Quickstart — 3 lines to generate your first app.

Usage:
    export SAC_API_KEY="sk-..."
    python examples/quickstart.py
"""

import asyncio
import os

from sac import SaC


async def main():
    sac = SaC(api_key=os.environ["SAC_API_KEY"])
    app = await sac.generate("2026 travel guide for Hangzhou")
    print(app.code)
    await sac.close()


if __name__ == "__main__":
    asyncio.run(main())
