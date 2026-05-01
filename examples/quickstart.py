"""
SaC Quickstart — generate an app, evolve it, see it in your browser.

Setup:
    export SAC_API_KEY="sk-or-..."        # OpenRouter key
    # optional, enables real-time data:
    export SAC_SEARCH_API_KEY="tvly-..."  # Tavily key

Run:
    python examples/quickstart.py

What this demonstrates:
    1. Conversation is the primitive — you hold a `conv`, not isolated apps.
    2. `evolve` carries state forward — SaC decides what to change, not regenerate.
    3. Persistence — conversations live in ./.sac/ so you can reopen them later.

To see what you generated, in another terminal run:
    sac serve
Then open http://localhost:8000 and pick your conversation from the sidebar.
"""

import asyncio
import os

from sac import SaC


async def main() -> None:
    sac = SaC(
        api_key=os.environ["SAC_API_KEY"],
        search_api_key=os.environ.get("SAC_SEARCH_API_KEY"),
    )

    # Conversation is the unit of value — it holds state, history, and the
    # chain of evolving App versions. Hold onto `conv`, not the App.
    conv = sac.conversation()

    print("→ Generating v1 ...")
    app = await conv.generate("3-day Tokyo itinerary for a first-time visitor")
    print(f"  v{app.version} ready ({len(app.code):,} chars)")

    # evolve != regenerate. SaC inspects the previous app, decides what to
    # change (extend the current view vs add a new section), and only modifies
    # what's needed.
    print("→ Evolving to v2 ...")
    app = await conv.evolve("add restaurant picks for each day")
    print(f"  v{app.version} ready ({len(app.code):,} chars)")
    if app.growth_decision:
        print(f"  decision: {app.growth_decision.growth_type} — {app.growth_decision.reason}")

    print()
    print(f"Conversation id: {conv.id}")
    print(f"Persisted to:    ./.sac/")
    print()
    print("To see it: run `sac serve` in another terminal,")
    print("then open http://localhost:8000 and pick this conversation from the sidebar.")

    await sac.close()


if __name__ == "__main__":
    asyncio.run(main())
