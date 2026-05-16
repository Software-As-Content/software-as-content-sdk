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

    # sac publish
    pub_parser = subparsers.add_parser(
        "publish",
        help="Publish content to a running SaC server",
    )
    pub_parser.add_argument(
        "content", nargs="?", default=None,
        help="Markdown content to publish (omit to read from stdin)",
    )
    pub_parser.add_argument(
        "-f", "--file", default=None,
        help="Read content from a file instead of positional arg / stdin",
    )
    pub_parser.add_argument("--intent", default=None, help="Short description of the content")
    pub_parser.add_argument("--conversation-id", default=None, help="Update an existing conversation")
    pub_parser.add_argument(
        "--server", default=None,
        help="SaC server URL (default: http://127.0.0.1:8000)",
    )
    pub_parser.add_argument(
        "--callback-url", default=None,
        help="Callback URL for interactive actions (e.g. codex://resume?thread=last&cwd=server)",
    )
    pub_parser.add_argument(
        "--callback-format", default=None,
        help="Callback format (e.g. codex_exec_resume)",
    )

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

    elif args.command == "publish":
        _publish(args)

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


def _publish(args: argparse.Namespace) -> None:
    """Publish content to a running SaC server via /inbox."""
    import json
    import urllib.request

    # Resolve content
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
    elif args.content:
        content = args.content
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        print("Error: provide content as argument, --file, or pipe via stdin", file=sys.stderr)
        sys.exit(1)

    if not content.strip():
        print("Error: content is empty", file=sys.stderr)
        sys.exit(1)

    server = (args.server or os.environ.get("SAC_SERVER", "") or "http://127.0.0.1:8000").rstrip("/")

    payload: dict[str, str] = {"content": content}
    if args.intent:
        payload["intent"] = args.intent
    if args.conversation_id:
        payload["conversation_id"] = args.conversation_id
    if args.callback_url:
        payload["callback_url"] = args.callback_url
    if args.callback_format:
        payload["callback_format"] = args.callback_format

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"{server}/inbox"

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=300)
        result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        print(f"Error: cannot reach SaC server at {server}: {exc}", file=sys.stderr)
        print("Start the server with: sac serve", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Print result
    app_url = result.get("url", "")
    conv_id = result.get("conversation_id", "")
    version = result.get("version")
    result_type = result.get("type", "")

    if app_url:
        print(app_url)
    if conv_id:
        print(f"  conversation_id: {conv_id}", file=sys.stderr)
    if version is not None:
        print(f"  version: {version}", file=sys.stderr)
    if result_type:
        print(f"  type: {result_type}", file=sys.stderr)


if __name__ == "__main__":
    main()
