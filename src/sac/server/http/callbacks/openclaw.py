"""OpenClaw callback adapters for the HTTP server."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any


async def openclaw_gateway_send(
    ws_url: str,
    token: str,
    session_key: str,
    message: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send a message to an OpenClaw agent session via Gateway WebSocket RPC."""
    try:
        import websockets
    except ImportError:
        raise RuntimeError(
            "websockets package required for OpenClaw callback. "
            "Install with: pip install websockets"
        )

    async with websockets.connect(ws_url, max_size=25 * 1024 * 1024) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        challenge = json.loads(raw)
        if challenge.get("event") != "connect.challenge":
            raise RuntimeError(f"Expected connect.challenge, got: {challenge}")

        connect_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 4,
                "client": {
                    "id": "gateway-client",
                    "version": "0.1.0",
                    "platform": "sac-sdk",
                    "mode": "backend",
                },
                "caps": [],
                "role": "operator",
                "scopes": ["operator.write"],
                "auth": {"token": token},
            },
        }))

        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        hello = json.loads(raw)
        if not (hello.get("type") == "res" and hello.get("ok")):
            raise RuntimeError(f"Gateway auth failed: {hello}")

        send_id = str(uuid.uuid4())
        await ws.send(json.dumps({
            "type": "req",
            "id": send_id,
            "method": "sessions.send",
            "params": {
                "key": session_key,
                "message": message,
                "idempotencyKey": str(uuid.uuid4()),
            },
        }))

        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            frame = json.loads(raw)
            if frame.get("type") == "res" and frame.get("id") == send_id:
                if frame.get("ok"):
                    return frame.get("payload", {})
                raise RuntimeError(f"sessions.send failed: {frame.get('error')}")


def build_gateway_message(
    *,
    intent: str,
    conv_id: str,
    sac_url: str,
) -> str:
    return (
        f"A user is viewing a SaC interactive app and requested: {intent}\n\n"
        f"Your `intent` and `content` should describe WHAT to show — do NOT include UI styling directions "
        f"(colors, dark/light theme, CSS classes, layout instructions). SaC controls visual design autonomously.\n\n"
        f"Compose rich, detailed content for this request, then run this exact command "
        f"(replace CONTENT with your composed content, escape quotes and newlines for JSON):\n\n"
        f'exec: curl -s -X POST "{sac_url}/inbox" '
        f'-H "Content-Type: application/json" '
        f"-d '{{\"conversation_id\": \"{conv_id}\", "
        f"\"content\": \"CONTENT\", "
        f"\"intent\": \"{intent}\"}}'\n\n"
        f"Do NOT ask clarifying questions — just compose the best content you can and run the curl command."
    )
