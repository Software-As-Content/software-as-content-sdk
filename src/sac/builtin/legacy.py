"""
LegacyShim — transitional adapter for the pre-protocol-pivot API surface.

Houses two operations that exist only because the SaC product (sac-web) and
the MCP server were built against the old "Conversation has classify/send"
API. In the dual-channel protocol end-state both dissolve:

  - `classify(message)` — chat vs update LLM call. Replaced by the fused
    LLM call inside core's renderer (which decides chat vs ui from the
    response shape itself; no separate classifier needed).

  - `send(message)` — the "user types text → classify → dispatch to chat
    reply or generate/evolve" flow. In the new architecture, agents fill
    the appropriate channel (NL or Φˢ) and SaC reads the shape; there is
    no two-step classify+dispatch.

When the product migrates to the new protocol surface (post-fused-LLM
milestone), this entire file gets deleted.

NOTE: send() still drives generate/evolve through `Conversation.generate`
and `Conversation.evolve` delegates — so it transparently uses the
`StandaloneAgent` for the actual work. The shim only owns the
classify-and-dispatch routing layer.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sac.builtin.prompts.classify import CLASSIFY_COLD, CLASSIFY_WITH_CONTEXT
from sac.runtime.providers.base import LLMProvider
from sac.types import (
    Message,
    MessageEvent,
    SendResult,
    SendResultType,
)

if TYPE_CHECKING:
    from sac.conversation import Conversation


class LegacyShim:
    """Compat layer for /send + /classify HTTP endpoints and conv.send()/classify()."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def send(self, conv: "Conversation", message: str, **opts: Any) -> SendResult:
        """Classify message → dispatch to chat reply or generate/evolve."""
        classification = await self.classify(conv, message)

        if classification["type"] == "chat":
            reply = classification.get("reply", "")
            await conv._store.add_event(
                MessageEvent(conversation_id=conv.id, role="user", content=message)
            )
            await conv._store.add_event(
                MessageEvent(conversation_id=conv.id, role="assistant", content=reply)
            )
            return SendResult(type=SendResultType.CHAT, reply=reply)

        # "update" — route via Conversation's delegate (which goes to StandaloneAgent)
        if conv.current_app is not None:
            app = await conv.evolve(message, **opts)
            return SendResult(type=SendResultType.EVOLVE, app=app)
        else:
            app = await conv.generate(message, **opts)
            return SendResult(type=SendResultType.GENERATE, app=app)

    async def classify(self, conv: "Conversation", message: str) -> dict:
        """Classify a user message as 'chat' or 'update' via LLM."""
        has_context = conv.current_app is not None
        system_prompt = CLASSIFY_WITH_CONTEXT if has_context else CLASSIFY_COLD

        user_content = message
        if has_context and conv.current_app:
            user_content = (
                f"[Current app intent: {conv.current_app.intent}]\n\nUser message: {message}"
            )

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

        try:
            raw = await self._llm.complete(conv.model, messages, max_tokens=256)
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()
            return json.loads(text)
        except (json.JSONDecodeError, Exception):
            return {"type": "update"}
