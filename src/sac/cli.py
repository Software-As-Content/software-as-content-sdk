"""
SaC CLI

Command-line interface for the SaC SDK.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env file from current working directory if it exists."""
    env_file = Path.cwd() / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(prog="sac", description="Software as Content SDK")
    subparsers = parser.add_subparsers(dest="command")

    # sac serve
    serve_parser = subparsers.add_parser("serve", help="Start the SaC HTTP/SSE server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    serve_parser.add_argument("--transport", choices=["http", "stdio"], default="http", help="Transport mode")

    # sac generate
    gen_parser = subparsers.add_parser("generate", help="Generate an app from an intent")
    gen_parser.add_argument("intent", help="The user intent / prompt")
    gen_parser.add_argument("--model", default=None, help="Model to use")
    gen_parser.add_argument("--no-search", action="store_true", help="Disable web search")

    args = parser.parse_args()

    if args.command == "serve":
        if args.transport == "stdio":
            try:
                from sac.server.mcp import run_stdio
            except ImportError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            run_stdio()
            return
        from sac.server.http import run
        run(host=args.host, port=args.port)

    elif args.command == "generate":
        asyncio.run(_generate(args))

    else:
        parser.print_help()


async def _generate(args: argparse.Namespace) -> None:
    import os
    from sac.sac import SaC

    api_key = os.environ.get("SAC_API_KEY", "")
    if not api_key:
        print("Error: SAC_API_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    sac = SaC(
        api_key=api_key,
        search_api_key=os.environ.get("SAC_SEARCH_API_KEY"),
    )

    try:
        app = await sac.generate(
            args.intent,
            model=args.model,
            web_search=not args.no_search,
        )
        print(app.code)
    finally:
        await sac.close()


if __name__ == "__main__":
    main()
