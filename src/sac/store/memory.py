"""
In-Memory Conversation Store

Default store implementation backed by Python dicts. Zero setup, no persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sac.types import ConversationData, ConversationEvent


class MemoryStore:
    """In-memory conversation store (default). Data is lost when the process exits."""

    def __init__(self) -> None:
        self._conversations: dict[str, ConversationData] = {}
        self._events: dict[str, list[ConversationEvent]] = {}

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
