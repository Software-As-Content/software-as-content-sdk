"""
In-Memory Conversation Store

Default store implementation backed by Python dicts.
Optionally writes generated code to disk when output_dir is set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sac.types import ConversationData, ConversationEvent


class MemoryStore:
    """
    In-memory conversation store (default).

    Args:
        output_dir: If set, writes generated code to disk on each successful
                    generation/growth event. Structure: {output_dir}/{conv_id}/v{n}.tsx
    """

    def __init__(self, output_dir: Path | str | None = None) -> None:
        self._conversations: dict[str, ConversationData] = {}
        self._events: dict[str, list[ConversationEvent]] = {}
        self._output_dir = Path(output_dir) if output_dir else None

    async def list_conversations(self) -> list[ConversationData]:
        convs = list(self._conversations.values())
        convs.sort(key=lambda c: c.updated_at, reverse=True)
        return convs

    async def get_conversation(self, id: str) -> ConversationData | None:
        return self._conversations.get(id)

    async def create_conversation(self, conv: ConversationData) -> None:
        self._conversations[conv.id] = conv
        self._events[conv.id] = []

    async def update_conversation(self, id: str, **updates: object) -> None:
        conv = self._conversations.get(id)
        if conv is None:
            return
        for key, value in updates.items():
            if hasattr(conv, key):
                setattr(conv, key, value)
        conv.updated_at = datetime.now(timezone.utc).isoformat()

    async def delete_conversation(self, id: str) -> None:
        self._conversations.pop(id, None)
        self._events.pop(id, None)

    async def get_events(self, conversation_id: str) -> list[ConversationEvent]:
        return list(self._events.get(conversation_id, []))

    async def add_event(self, event: ConversationEvent) -> None:
        conv_id = event.conversation_id
        if conv_id not in self._events:
            self._events[conv_id] = []
        self._events[conv_id].append(event)

        # Auto-update conversation metadata
        conv = self._conversations.get(conv_id)
        if conv is None:
            return

        conv.event_count = len(self._events[conv_id])
        conv.updated_at = event.timestamp

        if event.type in ("generation", "growth") and event.status == "success":
            if event.code:
                conv.latest_code = event.code
            conv.latest_intent = event.intent
            self._write_output(conv_id, event)

    def _write_output(self, conv_id: str, event: ConversationEvent) -> None:
        """Write generated code to disk if output_dir is set."""
        if self._output_dir is None:
            return
        # Count successful generations so far for version number
        version = sum(
            1 for e in self._events.get(conv_id, [])
            if e.type in ("generation", "growth") and e.status == "success"
        )
        conv_dir = self._output_dir / conv_id
        conv_dir.mkdir(parents=True, exist_ok=True)
        (conv_dir / f"v{version}.tsx").write_text(event.code, encoding="utf-8")
