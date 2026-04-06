"""
Multi-turn conversation — generate, then evolve.

Usage:
    export SAC_API_KEY="sk-..."
    export SAC_SEARCH_API_KEY="tvly-..."  # optional, enables web search
    python examples/conversation.py
"""

import asyncio
import os

from sac import SaC


async def main():
    sac = SaC(
        api_key=os.environ["SAC_API_KEY"],
        search_api_key=os.environ.get("SAC_SEARCH_API_KEY"),
    )

    conv = sac.conversation()

    # First generation
    app = await conv.generate("travel guide for Hangzhou", web_search=True)
    print(f"v{app.version}: Generated ({len(app.code)} chars)")
    print(f"  Suggestions: {[s.label for s in app.suggestions]}")

    # Evolve with new intent
    app = await conv.evolve("add restaurant recommendations")
    print(f"v{app.version}: Evolved ({len(app.code)} chars)")
    if app.growth_decision:
        print(f"  Decision: {app.growth_decision.growth_type} — {app.growth_decision.reason}")

    # Evolve again
    app = await conv.evolve("make it an interactive map")
    print(f"v{app.version}: Evolved ({len(app.code)} chars)")

    print(f"\nConversation has {conv.version} versions")
    await sac.close()


if __name__ == "__main__":
    asyncio.run(main())
