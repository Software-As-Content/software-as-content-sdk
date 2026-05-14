"""Callback dispatch and run tracking for the HTTP server."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
import uuid

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


class CallbackManager:
    """Dispatch SaC app actions to external agents and stream callback status."""

    def __init__(self, *, publish: PublishEvent, server_cwd: Path) -> None:
        self._publish = publish
        self._server_cwd = server_cwd
        self._runs: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def list_runs(self, conv_id: str) -> list[dict[str, Any]]:
        return self._runs.get(conv_id, [])

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
        if run.get("status") in {"succeeded", "failed"} and "completed_at" not in run:
            run["completed_at"] = run["updated_at"]
        self._publish(conv_id, "callback_run", run)
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
        entry = {
            "run_id": run_id,
            "stream": stream,
            "line": line[:2000],
            "payload": payload,
            "timestamp": self._utc_now(),
        }
        run = next((r for r in self._runs.get(conv_id, []) if r["id"] == run_id), None)
        if run is not None:
            logs = run.setdefault("logs", [])
            logs.append(entry)
            del logs[:-100]
        self._publish(conv_id, "callback_log", entry)

    def _publish_failure(self, conv_id: str, message: str) -> None:
        self._publish(conv_id, "chat", {"role": "system", "content": message})

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

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
