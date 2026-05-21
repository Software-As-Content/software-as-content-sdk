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

from sac import __version__


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
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # sac serve
    serve_parser = subparsers.add_parser("serve", help="Start the SaC HTTP/SSE server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=18420, help="Port to listen on (default: 18420)")
    serve_parser.add_argument("--transport", choices=["http", "stdio"], default="http", help="Transport mode")

    # sac generate
    gen_parser = subparsers.add_parser("generate", help="Generate an app from an intent")
    gen_parser.add_argument("intent", help="The user intent / prompt")
    gen_parser.add_argument("--model", default=None, help="Model to use")
    gen_parser.add_argument("--no-search", action="store_true", help="Disable web search")

    # sac setup
    setup_parser = subparsers.add_parser(
        "setup",
        help="Configure SaC for an agent platform",
    )
    setup_sub = setup_parser.add_subparsers(dest="platform")
    cc_parser = setup_sub.add_parser(
        "claude-code",
        help="Set up SaC as an MCP server for Claude Code",
    )
    cc_parser.add_argument(
        "--remove", action="store_true",
        help="Remove the SaC MCP server from Claude Code",
    )
    codex_parser = setup_sub.add_parser(
        "codex",
        help="Install the SaC skill for Codex",
    )
    codex_parser.add_argument(
        "--remove", action="store_true",
        help="Remove the SaC skill from Codex",
    )
    openclaw_parser = setup_sub.add_parser(
        "openclaw",
        help="Install the SaC skill for OpenClaw",
    )
    openclaw_parser.add_argument(
        "--remove", action="store_true",
        help="Remove the SaC skill from OpenClaw",
    )

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
        help="SaC server URL (default: http://127.0.0.1:18420)",
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

    elif args.command == "setup":
        if args.platform == "claude-code":
            _setup_claude_code(args)
        elif args.platform in ("codex", "openclaw"):
            _setup_skill(args.platform, remove=args.remove)
        else:
            setup_parser.print_help()

    elif args.command == "publish":
        _publish(args)

    else:
        parser.print_help()


def _setup_skill(platform: str, *, remove: bool = False) -> None:
    """Install or remove a SaC SKILL.md for Codex or OpenClaw."""
    from sac._skills import SKILL_TARGETS

    target = SKILL_TARGETS[platform]
    dest = Path(target["dest"]).expanduser()
    label = target["label"]

    if remove:
        skill_dir = dest.parent
        if skill_dir.exists():
            import shutil
            shutil.rmtree(skill_dir)
            print(f"  ✓ Removed SaC skill from {label} ({skill_dir})")
        else:
            print(f"  ✗ No SaC skill found for {label}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(target["content"], encoding="utf-8")
    print()
    print(f"  ✓ SaC skill installed for {label}")
    print(f"    {dest}")
    print()
    print(f"  Make sure the SaC server is running:")
    print(f"    sac serve")
    print()


def _get_desktop_config_path() -> Path | None:
    """Return the Claude Desktop config file path for this platform."""
    import platform
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif system == "Linux":
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    return None


def _setup_claude_code(args: argparse.Namespace) -> None:
    """Set up or remove SaC as an MCP server for Claude Code."""
    import json
    import shutil
    import subprocess

    # ── Remove ──────────────────────────────────────────────────
    if args.remove:
        print("Removing SaC MCP server from Claude Code...")
        removed = False

        # 1. Desktop config
        desktop_config = _get_desktop_config_path()
        if desktop_config and desktop_config.exists():
            try:
                config = json.loads(desktop_config.read_text(encoding="utf-8"))
                if "sac" in config.get("mcpServers", {}):
                    config["mcpServers"].pop("sac")
                    if not config["mcpServers"]:
                        config.pop("mcpServers")
                    desktop_config.write_text(
                        json.dumps(config, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(f"  ✓ Removed from Desktop config")
                    removed = True
            except Exception as exc:
                print(f"  ✗ Failed to update Desktop config: {exc}")

        # 2. CLI config (project scope)
        claude_path = shutil.which("claude")
        if claude_path:
            for scope in ("project", "user", "local"):
                result = subprocess.run(
                    ["claude", "mcp", "remove", "-s", scope, "sac"],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    print(f"  ✓ Removed from CLI {scope} config")
                    removed = True

        # 3. Remove .claude/launch.json if it's ours
        launch_file = Path.cwd() / ".claude" / "launch.json"
        if launch_file.exists():
            try:
                launch_data = json.loads(launch_file.read_text(encoding="utf-8"))
                configs = launch_data.get("configurations", [])
                if any(c.get("name") == "sac-viewer" for c in configs):
                    remaining = [c for c in configs if c.get("name") != "sac-viewer"]
                    if remaining:
                        launch_data["configurations"] = remaining
                        launch_file.write_text(
                            json.dumps(launch_data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8",
                        )
                    else:
                        launch_file.unlink()
                    print(f"  ✓ Removed preview config (.claude/launch.json)")
                    removed = True
            except Exception as exc:
                print(f"  ⚠ Failed to clean launch.json: {exc}")

        if not removed:
            print("  ✗ No SaC server found in any config")
        else:
            print()
            print("Restart Claude Code to apply changes.")
        return

    # ── Setup ───────────────────────────────────────────────────
    print()
    print("SaC MCP Setup for Claude Code")
    print("─" * 30)
    print()

    # Check prerequisites
    print("Checking prerequisites...")

    sac_path = shutil.which("sac")
    if not sac_path:
        print("  ✗ sac CLI not found on PATH")
        print("    Install with: pip install sac-sdk")
        sys.exit(1)
    print(f"  ✓ sac CLI: {sac_path}")

    # Provider selection
    print()
    print("LLM Provider (used by SaC to generate/update apps, not your agent)")
    print()
    print("  1) OpenRouter (default) — one key, all models")
    print("  2) Anthropic — Claude models directly")
    print("  3) OpenAI — GPT models directly")
    print("  4) Custom — any OpenAI-compatible endpoint")
    provider_choice = input("  Choose [1]: ").strip() or "1"

    api_base = ""
    key_label = "OpenRouter"
    if provider_choice == "2":
        key_label = "Anthropic"
    elif provider_choice == "3":
        api_base = "https://api.openai.com/v1/chat/completions"
        key_label = "OpenAI"
    elif provider_choice == "4":
        api_base = input("  Endpoint URL: ").strip()
        if not api_base:
            print("  ✗ Endpoint URL is required for custom provider")
            sys.exit(1)
        key_label = "Custom"

    print()
    print("API Keys")
    print()

    api_key = os.environ.get("SAC_API_KEY", "")
    if api_key:
        masked = api_key[:8] + "..." + api_key[-4:]
        use_env = input(f"  SAC_API_KEY found in env: {masked}. Use it? [Y/n] ").strip().lower()
        if use_env in ("n", "no"):
            api_key = ""

    if not api_key:
        api_key = input(f"  SAC_API_KEY ({key_label}): ").strip()
        if not api_key:
            print("  ✗ SAC_API_KEY is required")
            sys.exit(1)

    search_key = os.environ.get("SAC_SEARCH_API_KEY", "")
    if search_key:
        masked = search_key[:8] + "..." + search_key[-4:]
        use_env = input(f"  SAC_SEARCH_API_KEY found in env: {masked}. Use it? [Y/n] ").strip().lower()
        if use_env in ("n", "no"):
            search_key = ""

    if not search_key:
        search_key = input("  SAC_SEARCH_API_KEY (Tavily, Enter to skip): ").strip()

    data_dir = os.environ.get("SAC_DATA_DIR", "")
    if not data_dir:
        default_dir = str(Path.home() / ".sac")
        data_dir = input(f"  SAC_DATA_DIR [{default_dir}]: ").strip() or default_dir

    from sac.runtime.prompts.app import AVAILABLE_MODELS, DEFAULT_MODEL

    # Recommended models per provider (fast, reliable, cost-effective)
    RECOMMENDED = {
        "anthropic": "anthropic/claude-haiku-4.5",
        "openai": "openai/gpt-5.4-mini",
        "google": "google/gemini-3-flash-preview",
    }

    if provider_choice == "2":
        provider_models = [m for m in AVAILABLE_MODELS if m.provider == "anthropic"]
        default_model = RECOMMENDED["anthropic"]
        print()
        print("Model Selection")
        for m in provider_models:
            rec = " (recommended)" if m.id == default_model else ""
            print(f"  - {m.id}{rec}")
    elif provider_choice == "3":
        provider_models = [m for m in AVAILABLE_MODELS if m.provider == "openai"]
        default_model = RECOMMENDED["openai"]
        print()
        print("Model Selection")
        for m in provider_models:
            rec = " (recommended)" if m.id == default_model else ""
            print(f"  - {m.id}{rec}")
    else:
        default_model = DEFAULT_MODEL
        print()
        print("Model Selection")
        rec_ids = set(RECOMMENDED.values())
        for m in AVAILABLE_MODELS:
            rec = " (recommended)" if m.id in rec_ids else ""
            print(f"  - {m.id}{rec}")

    model = input(f"  SAC_MODEL [{default_model}]: ").strip() or default_model

    # Build server entry
    env = {"SAC_API_KEY": api_key, "SAC_DATA_DIR": data_dir, "SAC_MODEL": model}
    if api_base:
        env["SAC_API_BASE"] = api_base
    server_entry = {
        "command": sac_path,
        "args": ["serve", "--transport", "stdio"],
        "env": env,
    }
    if search_key:
        server_entry["env"]["SAC_SEARCH_API_KEY"] = search_key

    print()
    print("Configuring MCP server...")
    installed = False

    # 1. Desktop config
    desktop_config = _get_desktop_config_path()
    if desktop_config:
        try:
            if desktop_config.exists():
                config = json.loads(desktop_config.read_text(encoding="utf-8"))
            else:
                desktop_config.parent.mkdir(parents=True, exist_ok=True)
                config = {}
            config.setdefault("mcpServers", {})["sac"] = server_entry
            desktop_config.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  ✓ Desktop config")
            installed = True
        except Exception as exc:
            print(f"  ✗ Desktop config failed: {exc}")

    # 2. CLI config (project scope)
    claude_path = shutil.which("claude")
    if claude_path:
        env_args = ["-e", f"SAC_API_KEY={api_key}"]
        if api_base:
            env_args += ["-e", f"SAC_API_BASE={api_base}"]
        if search_key:
            env_args += ["-e", f"SAC_SEARCH_API_KEY={search_key}"]
        env_args += ["-e", f"SAC_DATA_DIR={data_dir}"]
        env_args += ["-e", f"SAC_MODEL={model}"]

        result = subprocess.run(
            ["claude", "mcp", "add", "-s", "project"] + env_args
            + ["--", "sac", sac_path, "serve", "--transport", "stdio"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"  ✓ CLI project config")
            installed = True
        else:
            print(f"  ⚠ CLI config skipped: {(result.stderr or result.stdout).strip()}")

    if not installed:
        print("  ✗ Failed to write any config")
        sys.exit(1)

    # 3. Write .claude/launch.json for built-in preview
    print()
    print("Configuring preview server...")
    launch_dir = Path.cwd() / ".claude"
    launch_file = launch_dir / "launch.json"
    try:
        python_path = sys.executable
        # Health check probes 18420 first, then 18421 (matches MCP server fallback)
        health_script = (
            "import time, urllib.request, json, sys\n"
            "port = None\n"
            "for p in (18420, 18421):\n"
            "    try:\n"
            "        r = urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=2)\n"
            "        d = json.loads(r.read())\n"
            "        if d.get('status') == 'ok':\n"
            "            port = p; break\n"
            "    except Exception: pass\n"
            "if not port:\n"
            "    print('SaC server not found on 18420/18421', file=sys.stderr); sys.exit(1)\n"
            "print(f'Connected to SaC server at http://127.0.0.1:{port}')\n"
            "while True: time.sleep(3600)"
        )
        launch_config = {
            "version": "0.0.1",
            "configurations": [
                {
                    "name": "sac-viewer",
                    "runtimeExecutable": python_path,
                    "runtimeArgs": ["-c", health_script],
                    "port": 18420,
                }
            ],
        }
        launch_dir.mkdir(parents=True, exist_ok=True)
        launch_file.write_text(
            json.dumps(launch_config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  ✓ Preview config (.claude/launch.json)")
    except Exception as exc:
        print(f"  ⚠ Preview config skipped: {exc}")

    print()
    print("Done! Restart Claude Code to activate SaC tools:")
    print("  generate_app, evolve_app, wait_for_action,")
    print("  list_conversations, get_conversation")
    print()


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

    server = (args.server or os.environ.get("SAC_SERVER", "") or "http://127.0.0.1:18420").rstrip("/")

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
