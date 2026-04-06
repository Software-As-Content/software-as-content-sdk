"""
SaC SDK — local development entry point.

Loads .env, runs example usage.
Output written to output/{conversation_id}/v{version}.tsx

Usage:
    python main.py
"""

import asyncio
import os
from pathlib import Path


def load_dotenv() -> None:
    """Load .env file from project root."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


from sac import SaC  # noqa: E402
from sac.store.memory import MemoryStore  # noqa: E402


async def main():
    sac = SaC(
        api_key=os.environ["SAC_API_KEY"],
        search_api_key=os.environ.get("SAC_SEARCH_API_KEY"),
        store=MemoryStore(output_dir="output"),
    )

    conv = sac.conversation()

    app = await conv.generate("2026 travel guide for Hangzhou")
    print(f"v{app.version} | {len(app.code)} chars | suggestions: {[s.label for s in app.suggestions]}")

    app = await conv.evolve("add restaurant recommendations")
    print(f"v{app.version} | {len(app.code)} chars | growth: {app.growth_decision}")

    print(f"\nConversation {conv.id} has {conv.version} versions")
    print(f"Output: output/{conv.id}/")

    await sac.close()


if __name__ == "__main__":
    asyncio.run(main())
