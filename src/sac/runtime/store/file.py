"""
File-based Conversation Store

Persists conversations and events as JSON files on disk.
Structure:
    {data_dir}/
        conversations.json          ← conversation metadata index
        {conv_id}/
            events.json             ← event history
            v1.tsx, v2.tsx, ...     ← generated code snapshots
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sac.types import (
    ConversationData,
    ConversationEvent,
    ErrorEvent,
    GenerationEvent,
    GrowthEvent,
    MessageEvent,
)

# Map event type strings to their Pydantic model classes
_EVENT_CLASSES: dict[str, type[ConversationEvent]] = {
    "message": MessageEvent,
    "generation": GenerationEvent,
    "growth": GrowthEvent,
    "error": ErrorEvent,
}


class FileStore:
    """
    File-based conversation store.

    Stores conversation metadata in a single index file and events
    per conversation in individual directories. Generated code is also
    written as .tsx files for easy inspection.

    Args:
        data_dir: Directory to store all data. Created if it doesn't exist.
    """

    def __init__(self, data_dir: Path | str = ".sac") -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "conversations.json"
        self._conversations: dict[str, ConversationData] = {}
        self._load_index()

    # ─── ConversationStore Protocol ───────────────────────────────

    async def list_conversations(self) -> list[ConversationData]:
        convs = list(self._conversations.values())
        convs.sort(key=lambda c: c.updated_at, reverse=True)
        return convs

    async def get_conversation(self, id: str) -> ConversationData | None:
        return self._conversations.get(id)

    async def create_conversation(self, conv: ConversationData) -> None:
        self._conversations[conv.id] = conv
        conv_dir = self._dir / conv.id
        conv_dir.mkdir(parents=True, exist_ok=True)
        self._save_index()
        self._save_events(conv.id, [])

    async def update_conversation(self, id: str, **updates: object) -> None:
        conv = self._conversations.get(id)
        if conv is None:
            return
        for key, value in updates.items():
            if hasattr(conv, key):
                setattr(conv, key, value)
        conv.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_index()

    async def delete_conversation(self, id: str) -> None:
        self._conversations.pop(id, None)
        self._save_index()
        # Remove conversation directory
        conv_dir = self._dir / id
        if conv_dir.exists():
            import shutil
            shutil.rmtree(conv_dir)

    async def get_events(self, conversation_id: str) -> list[ConversationEvent]:
        return self._load_events(conversation_id)

    async def add_event(self, event: ConversationEvent) -> None:
        conv_id = event.conversation_id
        events = self._load_events(conv_id)
        events.append(event)
        self._save_events(conv_id, events)

        # Auto-update conversation metadata
        conv = self._conversations.get(conv_id)
        if conv is None:
            return

        conv.event_count = len(events)
        conv.updated_at = event.timestamp

        if event.type in ("generation", "growth") and event.status == "success":
            if event.code:
                conv.latest_code = event.code
                self._write_code(conv_id, events)
            conv.latest_intent = event.intent

        self._save_index()

    # ─── Private helpers ──────────────────────────────────────────

    def _load_index(self) -> None:
        """Load conversation index from disk."""
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            for item in data:
                conv = ConversationData(**item)
                self._conversations[conv.id] = conv
        except (json.JSONDecodeError, Exception):
            pass

    def _save_index(self) -> None:
        """Save conversation index to disk."""
        data = [c.model_dump() for c in self._conversations.values()]
        self._index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _events_path(self, conv_id: str) -> Path:
        return self._dir / conv_id / "events.json"

    def _load_events(self, conv_id: str) -> list[ConversationEvent]:
        """Load events from disk."""
        path = self._events_path(conv_id)
        if not path.exists():
            return []
        try:
            raw_list: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
            events: list[ConversationEvent] = []
            for item in raw_list:
                event_type = item.get("type", "")
                cls = _EVENT_CLASSES.get(event_type)
                if cls:
                    events.append(cls(**item))
            return events
        except (json.JSONDecodeError, Exception):
            return []

    def _save_events(self, conv_id: str, events: list[ConversationEvent]) -> None:
        """Save events to disk."""
        conv_dir = self._dir / conv_id
        conv_dir.mkdir(parents=True, exist_ok=True)
        data = [e.model_dump() for e in events]
        self._events_path(conv_id).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_code(self, conv_id: str, events: list[ConversationEvent]) -> None:
        """Write generated code as .tsx file."""
        version = sum(
            1 for e in events
            if e.type in ("generation", "growth") and e.status == "success"
        )
        conv_dir = self._dir / conv_id
        conv_dir.mkdir(parents=True, exist_ok=True)
        code = ""
        for e in events:
            if e.type in ("generation", "growth") and e.status == "success" and e.code:
                code = e.code
        if code:
            (conv_dir / f"v{version}.tsx").write_text(code, encoding="utf-8")
