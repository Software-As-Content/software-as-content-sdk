"""Callback dispatch and run tracking for the HTTP server."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
import uuid

logger = logging.getLogger(__name__)

import httpx
from fastapi import HTTPException

from sac.server.http.callbacks.codex import (
    build_codex_message,
    codex_http_error,
    parse_codex_callback_url,
    run_codex_resume,
)
from sac.server.http.callbacks.openclaw import (
    build_gateway_message,
    openclaw_gateway_send,
)


PublishEvent = Callable[[str, str, dict[str, Any]], None]
PinThread = Callable[[str, str], "Any"]  # async (conv_id, thread_id) -> None


class CallbackManager:
    """Dispatch SaC app actions to external agents and stream callback status."""

    # Keys excluded from the on-disk snapshot (large / transient).
    _TRANSIENT_KEYS = frozenset({"stdout_tail", "stderr_tail", "context"})
    # Within each log entry, only these keys are persisted (the rest are large/raw).
    _LOG_PERSIST_KEYS = frozenset({"kind", "label", "detail", "raw_visible", "timestamp"})

    def __init__(
        self,
        *,
        publish: PublishEvent,
        server_cwd: Path,
        pin_thread: PinThread | None = None,
        runs_dir: Path | None = None,
    ) -> None:
        self._publish = publish
        self._server_cwd = server_cwd
        self._pin_thread = pin_thread
        self._runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._runs_dir = runs_dir
        if runs_dir is not None:
            runs_dir.mkdir(parents=True, exist_ok=True)

    def list_runs(self, conv_id: str) -> list[dict[str, Any]]:
        if conv_id not in self._runs and self._runs_dir is not None:
            self._load_runs(conv_id)
        return self._runs.get(conv_id, [])

    def _get_run(self, conv_id: str, run_id: str) -> dict[str, Any] | None:
        return next(
            (r for r in self._runs.get(conv_id, []) if r["id"] == run_id),
            None,
        )

    def has_active_run(self, conv_id: str) -> bool:
        """Check if there is a running/queued callback run for this conversation."""
        for run in reversed(self._runs.get(conv_id, [])):
            if run.get("status") in {"running", "queued"}:
                return True
        return False

    def mark_inbox_result(
        self,
        conv_id: str,
        *,
        kind: str,
        version: int | None,
    ) -> bool:
        """Record that the upstream agent posted back to ``/inbox``.

        A callback run is only a *real* success when the agent actually
        closes the loop by POSTing to ``/inbox`` (chat reply or new app
        version). Subprocess exit code alone does not prove the loop
        closed. This attaches the inbox outcome to the most recent
        in-flight run so the run's final status reflects whether the app
        actually changed.

        Returns ``True`` if an in-flight run was found and tagged. The
        initial publish (v1) has no in-flight callback run, so this is a
        no-op there — exactly what we want.
        """
        runs = self._runs.get(conv_id, [])
        for run in reversed(runs):
            if run.get("status") in {"running", "queued"}:
                run["loop_closed"] = True
                run["result_kind"] = kind
                run["result_version"] = version
                run["updated_at"] = self._utc_now()
                self._publish(conv_id, "callback_run", run)
                self._persist_runs(conv_id)
                return True
        return False

    async def dispatch(
        self,
        *,
        conv_id: str,
        intent: str,
        context: dict[str, Any] | None,
        callback_url: str,
        callback_format: str | None,
        callback_auth: str | None,
        sac_url: str,
    ) -> dict[str, Any]:
        fmt = self._infer_format(callback_url, callback_format)
        run = self._new_run(
            conv_id,
            adapter=fmt,
            intent=intent,
            callback_url=callback_url,
            context=context,
        )

        if fmt == "openclaw_gateway":
            await self._dispatch_openclaw_gateway(
                run=run,
                conv_id=conv_id,
                intent=intent,
                callback_url=callback_url,
                callback_auth=callback_auth,
                sac_url=sac_url,
            )
        elif fmt == "codex_exec_resume":
            self._dispatch_codex_resume(
                run=run,
                conv_id=conv_id,
                intent=intent,
                context=context,
                callback_url=callback_url,
                sac_url=sac_url,
            )
        elif fmt == "openclaw_taskflow":
            await self._dispatch_openclaw_taskflow(
                run=run,
                conv_id=conv_id,
                intent=intent,
                callback_url=callback_url,
                callback_auth=callback_auth,
                sac_url=sac_url,
            )
        else:
            await self._dispatch_default_http(
                run=run,
                conv_id=conv_id,
                intent=intent,
                context=context,
                callback_url=callback_url,
                callback_auth=callback_auth,
            )

        return run

    def _infer_format(self, callback_url: str, callback_format: str | None) -> str:
        fmt = callback_format or "default"
        callback_scheme = urlparse(callback_url).scheme
        if fmt == "default" and callback_scheme == "codex":
            return "codex_exec_resume"
        if fmt == "default" and callback_scheme in ("ws", "wss"):
            return "openclaw_gateway"
        return fmt

    def _new_run(
        self,
        conv_id: str,
        *,
        adapter: str,
        intent: str,
        callback_url: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        run = {
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "adapter": adapter,
            "intent": intent,
            "context": context,
            "callback_url": callback_url,
            "status": "queued",
            "created_at": self._utc_now(),
            "updated_at": self._utc_now(),
        }
        self._runs[conv_id].append(run)
        self._runs[conv_id] = self._runs[conv_id][-50:]
        self._publish(conv_id, "callback_run", run)
        self._persist_runs(conv_id)
        return run

    def _update_run(
        self,
        conv_id: str,
        run_id: str,
        **updates: Any,
    ) -> dict[str, Any] | None:
        runs = self._runs.get(conv_id, [])
        run = next((r for r in runs if r["id"] == run_id), None)
        if run is None:
            return None
        run.update(updates)
        run["updated_at"] = self._utc_now()
        if run.get("status") in {"succeeded", "failed", "no_update"} and "completed_at" not in run:
            run["completed_at"] = run["updated_at"]
        self._publish(conv_id, "callback_run", run)
        self._persist_runs(conv_id)
        return run

    def _publish_log(
        self,
        conv_id: str,
        run_id: str,
        *,
        stream: str,
        line: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        summary = self._summarize_log(stream=stream, line=line, payload=payload)
        entry = {
            "run_id": run_id,
            "stream": stream,
            "line": line[:2000],
            "payload": payload,
            "kind": summary["kind"],
            "label": summary["label"],
            "detail": summary.get("detail"),
            "raw_visible": summary.get("raw_visible", False),
            "timestamp": self._utc_now(),
        }
        run = next((r for r in self._runs.get(conv_id, []) if r["id"] == run_id), None)
        if run is not None:
            logs = run.setdefault("logs", [])
            logs.append(entry)
            del logs[:-100]
            run["last_event"] = entry["label"]
            run["last_log_at"] = entry["timestamp"]
        self._publish(conv_id, "callback_log", entry)

    def _publish_failure(self, conv_id: str, message: str) -> None:
        self._publish(conv_id, "chat", {"role": "system", "content": message})

    def _summarize_log(
        self,
        *,
        stream: str,
        line: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Convert adapter-specific output into a compact product-facing event."""
        if payload:
            typ = payload.get("type")
            if typ == "thread.started":
                return {
                    "kind": "thread_started",
                    "label": "Codex thread started",
                    "detail": payload.get("thread_id"),
                }
            if typ == "turn.started":
                return {"kind": "turn_started", "label": "Codex turn started"}
            if typ == "turn.completed":
                usage = payload.get("usage") or {}
                details = []
                if usage.get("input_tokens") is not None:
                    details.append(f"input {usage['input_tokens']}")
                if usage.get("output_tokens") is not None:
                    details.append(f"output {usage['output_tokens']}")
                return {
                    "kind": "turn_completed",
                    "label": "Codex turn completed",
                    "detail": ", ".join(details) if details else None,
                }
            if typ == "error":
                return {
                    "kind": "warning",
                    "label": payload.get("message") or "Codex warning",
                    "raw_visible": True,
                }

            item = payload.get("item") or {}
            item_type = item.get("type")
            if typ == "item.started":
                if item_type == "command_execution":
                    return {
                        "kind": "command_started",
                        "label": "Command started",
                        "detail": item.get("command"),
                    }
                return {
                    "kind": "tool_started",
                    "label": f"{self._humanize_item_type(item_type)} started",
                }
            if typ == "item.completed":
                if item_type == "command_execution":
                    exit_code = item.get("exit_code")
                    label = "Command completed"
                    if exit_code not in (None, 0):
                        label = f"Command failed ({exit_code})"
                    return {
                        "kind": "command_completed",
                        "label": label,
                        "detail": item.get("command"),
                        "raw_visible": bool(item.get("aggregated_output")),
                    }
                if item_type == "agent_message":
                    return {
                        "kind": "agent_message",
                        "label": "Codex message",
                        "detail": str(item.get("text") or "")[:900],
                    }
                return {
                    "kind": "tool_completed",
                    "label": f"{self._humanize_item_type(item_type)} completed",
                }

        raw = " ".join(str(line or "").split())
        if not raw:
            return {"kind": "log", "label": f"{stream} log"}
        if raw.startswith("{") and len(raw) > 500:
            return {
                "kind": "raw",
                "label": f"{stream} event",
                "detail": raw[:240] + "...",
                "raw_visible": False,
            }
        return {
            "kind": "log",
            "label": f"{stream} log",
            "detail": raw[:700],
            "raw_visible": True,
        }

    def _humanize_item_type(self, item_type: str | None) -> str:
        if not item_type:
            return "Codex item"
        return str(item_type).replace("_", " ").strip().capitalize()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ─── Runs persistence ────────────────────────────────────────

    def _runs_path(self, conv_id: str) -> Path | None:
        if self._runs_dir is None:
            return None
        return self._runs_dir / f"{conv_id}.json"

    def _persist_runs(self, conv_id: str) -> None:
        """Write current runs for *conv_id* to disk (fire-and-forget)."""
        path = self._runs_path(conv_id)
        if path is None:
            return
        runs = self._runs.get(conv_id, [])
        # Strip transient / large keys to keep the file small.
        compact = []
        for r in runs:
            entry = {k: v for k, v in r.items() if k not in self._TRANSIENT_KEYS}
            # Slim down logs: keep only the display-relevant fields per entry.
            if "logs" in entry and isinstance(entry["logs"], list):
                entry["logs"] = [
                    {k: v for k, v in log.items() if k in self._LOG_PERSIST_KEYS}
                    for log in entry["logs"]
                ]
            compact.append(entry)
        try:
            path.write_text(
                json.dumps(compact, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("failed to persist runs for %s", conv_id, exc_info=True)

    def _load_runs(self, conv_id: str) -> None:
        """Load persisted runs into the in-memory cache (once per conv)."""
        path = self._runs_path(conv_id)
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._runs[conv_id] = data[-50:]
        except Exception:
            logger.debug("failed to load runs for %s", conv_id, exc_info=True)

    async def _dispatch_openclaw_gateway(
        self,
        *,
        run: dict[str, Any],
        conv_id: str,
        intent: str,
        callback_url: str,
        callback_auth: str | None,
        sac_url: str,
    ) -> None:
        parsed = urlparse(callback_url)
        qs = parse_qs(parsed.query)
        session_key = (qs.get("session") or ["agent:main:main"])[0]
        ws_url = f"{parsed.scheme}://{parsed.netloc}"
        token = (callback_auth or "").removeprefix("Bearer ").strip()
        message = build_gateway_message(intent=intent, conv_id=conv_id, sac_url=sac_url)

        try:
            self._update_run(
                conv_id,
                run["id"],
                status="running",
                target_session=session_key,
                transport="websocket",
            )
            await openclaw_gateway_send(
                ws_url=ws_url,
                token=token,
                session_key=session_key,
                message=message,
            )
            self._update_run(
                conv_id,
                run["id"],
                status="succeeded",
                detail="Message sent to OpenClaw gateway.",
            )
        except Exception as exc:
            self._update_run(conv_id, run["id"], status="failed", error=str(exc))
            raise HTTPException(
                status_code=502,
                detail=f"Failed to send to OpenClaw gateway ({ws_url}): {exc}",
            )

    def _dispatch_codex_resume(
        self,
        *,
        run: dict[str, Any],
        conv_id: str,
        intent: str,
        context: dict[str, Any] | None,
        callback_url: str,
        sac_url: str,
    ) -> None:
        try:
            thread_id, cwd = parse_codex_callback_url(
                callback_url,
                server_cwd=self._server_cwd,
            )
        except ValueError as exc:
            self._update_run(conv_id, run["id"], status="failed", error=str(exc))
            raise codex_http_error(exc)

        message = build_codex_message(
            intent=intent,
            context=context,
            conv_id=conv_id,
            sac_url=sac_url,
        )
        asyncio.create_task(
            run_codex_resume(
                conv_id=conv_id,
                run_id=run["id"],
                thread_id=thread_id,
                cwd=cwd,
                message=message,
                update_run=self._update_run,
                publish_log=self._publish_log,
                publish_failure=self._publish_failure,
                get_run=self._get_run,
                on_thread=self._pin_thread,
            )
        )

    async def _dispatch_openclaw_taskflow(
        self,
        *,
        run: dict[str, Any],
        conv_id: str,
        intent: str,
        callback_url: str,
        callback_auth: str | None,
        sac_url: str,
    ) -> None:
        payload: dict[str, Any] = {
            "action": "create_flow",
            "goal": (
                f"SaC user action on conversation {conv_id}: "
                f"{intent}\n\n"
                f"Use the sac-interaction skill to POST updated content "
                f"to {sac_url}/inbox with conversation_id \"{conv_id}\"."
            ),
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if callback_auth:
            headers["Authorization"] = callback_auth
        await self._post_json(
            run=run,
            conv_id=conv_id,
            callback_url=callback_url,
            payload=payload,
            headers=headers,
        )

    async def _dispatch_default_http(
        self,
        *,
        run: dict[str, Any],
        conv_id: str,
        intent: str,
        context: dict[str, Any] | None,
        callback_url: str,
        callback_auth: str | None,
    ) -> None:
        payload: dict[str, Any] = {"conversation_id": conv_id, "intent": intent}
        if context is not None:
            payload["context"] = context
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if callback_auth:
            headers["Authorization"] = callback_auth
        await self._post_json(
            run=run,
            conv_id=conv_id,
            callback_url=callback_url,
            payload=payload,
            headers=headers,
        )

    async def _post_json(
        self,
        *,
        run: dict[str, Any],
        conv_id: str,
        callback_url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                self._update_run(
                    conv_id,
                    run["id"],
                    status="running",
                    transport="http",
                )
                response = await client.post(callback_url, json=payload, headers=headers)
                response.raise_for_status()
                self._update_run(
                    conv_id,
                    run["id"],
                    status="succeeded",
                    status_code=response.status_code,
                )
            except httpx.HTTPError as exc:
                self._update_run(conv_id, run["id"], status="failed", error=str(exc))
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to reach callback_url ({callback_url}): {exc}",
                )
