"""Codex CLI callback adapter for the HTTP server."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException


PublishLog = Callable[..., None]
UpdateRun = Callable[..., dict[str, Any] | None]
PublishFailure = Callable[[str, str], None]
GetRun = Callable[[str, str], dict[str, Any] | None]
OnThread = Callable[[str, str], Awaitable[None]]


def resolve_codex_cwd(raw_cwd: str, *, server_cwd: Path) -> str | None:
    """Resolve the working directory for Codex callback subprocesses."""
    value = raw_cwd.strip()
    if not value:
        return None
    if value in {"server", "."}:
        return str(server_cwd)

    path = Path(value).expanduser()
    if not path.is_dir():
        return str(server_cwd)

    project_markers = (".git", "pyproject.toml", "package.json", "src")
    looks_like_project = any((path / marker).exists() for marker in project_markers)
    server_looks_like_project = any(
        (server_cwd / marker).exists() for marker in project_markers
    )
    if not looks_like_project and server_looks_like_project:
        return str(server_cwd)

    return str(path)


def resolve_codex_bin() -> str:
    configured = os.environ.get("SAC_CODEX_BIN", "").strip()
    if configured:
        return configured

    found = shutil.which("codex")
    if found:
        return found

    app_bundle_bin = Path("/Applications/Codex.app/Contents/Resources/codex")
    if app_bundle_bin.exists():
        return str(app_bundle_bin)

    return "codex"


def parse_codex_callback_url(callback_url: str, *, server_cwd: Path) -> tuple[str, str | None]:
    parsed = urlparse(callback_url)
    if parsed.scheme != "codex" or parsed.netloc != "resume":
        raise ValueError(
            "Invalid Codex callback_url. Expected "
            "codex://resume?thread=<thread_id>&cwd=<absolute_path>."
        )
    qs = parse_qs(parsed.query)
    thread_id = (qs.get("thread") or qs.get("thread_id") or [""])[0].strip()
    if not thread_id:
        raise ValueError("Codex callback_url must include thread=<thread_id>.")
    cwd = resolve_codex_cwd((qs.get("cwd") or [""])[0], server_cwd=server_cwd)
    return thread_id, cwd


def build_codex_message(
    *,
    intent: str,
    context: dict[str, Any] | None,
    conv_id: str,
    sac_url: str,
) -> str:
    context_text = ""
    if context is not None:
        context_text = (
            "\n\nAction context JSON:\n"
            f"```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"
        )

    return (
        f"A user is viewing a SaC interactive app and requested: {intent}"
        f"{context_text}\n\n"
        f"Fast path contract:\n"
        f"- Treat this as a SaC UI action, not a general coding task.\n"
        f"- Do not inspect or modify the repo unless the action explicitly asks for engineering analysis or code changes.\n"
        f"- Use existing repository/session context first; do not run broad validation or debug unrelated infrastructure.\n"
        f"- Prefer concise, directly usable content that can update the current app within 60-120 seconds.\n"
        f"- Your `intent` and `content` should describe WHAT to show — do NOT include UI styling directions "
        f"(colors, dark/light theme, CSS classes, layout instructions). SaC controls visual design autonomously.\n\n"
        f"Compose rich, detailed content for the request, then run this exact command "
        f"(replace CONTENT with your composed content, escape quotes and newlines for JSON):\n\n"
        f'curl -s -X POST "{sac_url}/inbox" '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"conversation_id\": \"{conv_id}\", "
        f"\"content\": \"CONTENT\", "
        f"\"intent\": \"{intent}\"}}'\n\n"
        f"Do NOT ask clarifying questions. Do NOT only reply in chat. "
        f"Do the best follow-up analysis you can and update the SaC app via /inbox."
    )


async def run_codex_resume(
    *,
    conv_id: str,
    run_id: str,
    thread_id: str,
    cwd: str | None,
    message: str,
    update_run: UpdateRun,
    publish_log: PublishLog,
    publish_failure: PublishFailure,
    get_run: GetRun | None = None,
    on_thread: OnThread | None = None,
) -> None:
    codex_bin = resolve_codex_bin()
    cmd = [codex_bin]
    if cwd:
        cmd.extend(["-C", cwd])
    cmd.extend(["exec", "resume", "--json"])
    if thread_id == "last":
        cmd.append("--last")
    else:
        cmd.append(thread_id)
    cmd.append(message)
    command_preview = [*cmd[:-1], "<prompt>"]

    try:
        update_run(
            conv_id,
            run_id,
            status="running",
            cwd=cwd,
            command=command_preview,
            thread_id=thread_id,
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        captured_thread_id: str | None = None

        async def _read_lines(
            reader: asyncio.StreamReader | None,
            stream_name: str,
            sink: list[str],
        ) -> None:
            if reader is None:
                return
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode(errors="replace").rstrip("\n")
                if not line:
                    continue
                stored_line = line[:4000]
                sink.append(stored_line)
                del sink[:-100]
                payload = None
                stripped = line.strip()
                if stripped.startswith("{"):
                    try:
                        payload = json.loads(stripped)
                    except json.JSONDecodeError:
                        payload = None
                if (
                    payload
                    and payload.get("type") == "thread.started"
                    and payload.get("thread_id")
                ):
                    nonlocal captured_thread_id
                    captured_thread_id = str(payload["thread_id"])
                publish_log(
                    conv_id,
                    run_id,
                    stream=stream_name,
                    line=stored_line,
                    payload=payload,
                )

        await asyncio.gather(
            _read_lines(proc.stdout, "stdout", stdout_parts),
            _read_lines(proc.stderr, "stderr", stderr_parts),
        )
        await proc.wait()

        # G2: pin the resolved thread id so future callbacks target this
        # exact Codex thread instead of `--last` (which races with any
        # other Codex session started between publish and the next click).
        if thread_id == "last" and captured_thread_id and on_thread:
            try:
                await on_thread(conv_id, captured_thread_id)
                update_run(conv_id, run_id, thread_id=captured_thread_id)
            except Exception:
                pass

        stdout_tail = "\n".join(stdout_parts)[-4000:]
        stderr_tail = "\n".join(stderr_parts)[-4000:]
        if proc.returncode != 0:
            detail = stderr_tail or stdout_tail or f"exit code {proc.returncode}"
            update_run(
                conv_id,
                run_id,
                status="failed",
                returncode=proc.returncode,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
                error=detail.strip()[:1200],
            )
            publish_failure(conv_id, f"Codex callback failed ({detail.strip()[:1200]}).")
        else:
            run = get_run(conv_id, run_id) if get_run else None
            loop_closed = bool(run and run.get("loop_closed"))
            if loop_closed:
                update_run(
                    conv_id,
                    run_id,
                    status="succeeded",
                    returncode=proc.returncode,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                )
            else:
                # Subprocess exited cleanly but the agent never POSTed back
                # to /inbox — the app did not change. Surface this honestly
                # instead of a misleading green "succeeded".
                update_run(
                    conv_id,
                    run_id,
                    status="no_update",
                    returncode=proc.returncode,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                )
                publish_failure(
                    conv_id,
                    "Codex finished without updating the app "
                    "(no /inbox response). The app is unchanged.",
                )
    except FileNotFoundError:
        update_run(
            conv_id,
            run_id,
            status="failed",
            command=command_preview,
            error="Codex CLI not found.",
        )
        publish_failure(
            conv_id,
            "Codex callback failed: Codex CLI not found. "
            "Set SAC_CODEX_BIN to the absolute codex executable path.",
        )
    except Exception as exc:
        update_run(
            conv_id,
            run_id,
            status="failed",
            command=command_preview,
            error=str(exc),
        )
        publish_failure(conv_id, f"Codex callback failed: {exc}")


def codex_http_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "thread" in message:
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=400, detail=message)
