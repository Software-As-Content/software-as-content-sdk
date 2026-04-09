"""
Conversation Store Protocol

Abstract interface for conversation persistence.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sac.types import ConversationData, ConversationEvent


@runtime_checkable
class ConversationStore(Protocol):
    """Protocol for conversation persistence backends."""

    async def list_conversations(self, user_id: str = "") -> list[ConversationData]: ...

    async def get_conversation(self, id: str) -> ConversationData | None: ...

    async def create_conversation(self, conv: ConversationData) -> None: ...

    async def update_conversation(self, id: str, **updates: object) -> None: ...

    async def delete_conversation(self, id: str) -> None: ...

    async def get_events(self, conversation_id: str) -> list[ConversationEvent]: ...

    async def add_event(self, event: ConversationEvent) -> None: ...
