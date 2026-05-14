"""
File-based Conversation Store

Persists conversations and events as JSON files on disk.
Structure:
    {data_dir}/
        {user_id}/
            conversations.json          ← per-user conversation metadata index
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
    File-based conversation store with per-user directory isolation.

    Data is partitioned by user_id so each user has their own directory
    containing a conversations.json index and conversation subdirectories.

    Args:
        data_dir: Root directory to store all data. Created if it doesn't exist.
    """

    def __init__(self, data_dir: Path | str = ".sac") -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        # Per-user caches: user_id -> {conv_id -> ConversationData}
        self._users: dict[str, dict[str, ConversationData]] = {}
        # Reverse lookup: conv_id -> user_id
        self._conv_to_user: dict[str, str] = {}
        self._migrate_flat_layout()

    # ─── ConversationStore Protocol ───────────────────────────────

    async def list_conversations(self, user_id: str = "") -> list[ConversationData]:
        if not user_id:
            return []
        convs = list(self._get_user_index(user_id).values())
        convs.sort(key=lambda c: c.updated_at, reverse=True)
        return convs

    async def get_conversation(self, id: str) -> ConversationData | None:
        user_id = self._resolve_user_for_conversation(id)
        if user_id is None:
            return None
        return self._get_user_index(user_id).get(id)

    async def create_conversation(self, conv: ConversationData) -> None:
        user_id = conv.user_id or "anonymous"
        user_convs = self._get_user_index(user_id)
        if conv.id in user_convs:
            return
        user_convs[conv.id] = conv
        self._conv_to_user[conv.id] = user_id
        conv_dir = self._user_dir(user_id) / conv.id
        conv_dir.mkdir(parents=True, exist_ok=True)
        self._save_user_index(user_id)
        self._save_events(conv.id, [])

    async def update_conversation(self, id: str, **updates: object) -> None:
        user_id = self._resolve_user_for_conversation(id)
        if user_id is None:
            return
        conv = self._get_user_index(user_id).get(id)
        if conv is None:
            return
        for key, value in updates.items():
            if hasattr(conv, key):
                setattr(conv, key, value)
        conv.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_user_index(user_id)

    async def delete_conversation(self, id: str) -> None:
        user_id = self._resolve_user_for_conversation(id)
        if user_id is None:
            return
        self._conv_to_user.pop(id, None)
        self._get_user_index(user_id).pop(id, None)
        self._save_user_index(user_id)
        conv_dir = self._user_dir(user_id) / id
        if conv_dir.exists():
            import shutil
            shutil.rmtree(conv_dir)

    async def get_events(self, conversation_id: str) -> list[ConversationEvent]:
        return self._load_events(conversation_id)

    async def add_event(self, event: ConversationEvent) -> None:
        conv_id = event.conversation_id
        user_id = self._resolve_user_for_conversation(conv_id)
        if user_id is None:
            return

        events = self._load_events(conv_id)
        events.append(event)
        self._save_events(conv_id, events)

        conv = self._get_user_index(user_id).get(conv_id)
        if conv is None:
            return

        conv.event_count = len(events)
        conv.updated_at = event.timestamp

        if event.type in ("generation", "growth") and event.status == "success":
            if event.code:
                conv.latest_code = event.code
                self._write_code(conv_id, events)
            conv.latest_intent = event.intent

        self._save_user_index(user_id)

    # ─── Private helpers ──────────────────────────────────────────

    def _user_dir(self, user_id: str) -> Path:
        """Get the directory for a specific user."""
        d = self._dir / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _user_index_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "conversations.json"

    def _get_user_index(self, user_id: str) -> dict[str, ConversationData]:
        """Get or load the conversation index for a user."""
        if user_id not in self._users:
            self._load_user_index(user_id)
        return self._users[user_id]

    def _resolve_user_for_conversation(self, conv_id: str) -> str | None:
        """Find which user owns a conversation, including after process restart."""
        user_id = self._conv_to_user.get(conv_id)
        if user_id is not None:
            return user_id

        for loaded_user_id, convs in self._users.items():
            if conv_id in convs:
                self._conv_to_user[conv_id] = loaded_user_id
                return loaded_user_id

        for user_dir in self._dir.iterdir():
            if not user_dir.is_dir():
                continue
            index_path = user_dir / "conversations.json"
            if not index_path.exists():
                continue
            candidate_user_id = user_dir.name
            convs = self._get_user_index(candidate_user_id)
            if conv_id in convs:
                self._conv_to_user[conv_id] = candidate_user_id
                return candidate_user_id

        return None

    def _load_user_index(self, user_id: str) -> None:
        """Load a user's conversation index from disk."""
        self._users[user_id] = {}
        path = self._user_index_path(user_id)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data:
                conv = ConversationData(**item)
                self._users[user_id][conv.id] = conv
                self._conv_to_user[conv.id] = user_id
        except (json.JSONDecodeError, Exception):
            pass

    def _save_user_index(self, user_id: str) -> None:
        """Save a user's conversation index to disk."""
        convs = self._users.get(user_id, {})
        data = [c.model_dump() for c in convs.values()]
        self._user_index_path(user_id).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _conv_dir(self, conv_id: str) -> Path | None:
        """Get the directory for a conversation."""
        user_id = self._resolve_user_for_conversation(conv_id)
        if user_id is None:
            return None
        return self._user_dir(user_id) / conv_id

    def _events_path(self, conv_id: str) -> Path | None:
        d = self._conv_dir(conv_id)
        if d is None:
            return None
        return d / "events.json"

    def _load_events(self, conv_id: str) -> list[ConversationEvent]:
        """Load events from disk."""
        path = self._events_path(conv_id)
        if path is None or not path.exists():
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
        d = self._conv_dir(conv_id)
        if d is None:
            return
        d.mkdir(parents=True, exist_ok=True)
        data = [e.model_dump() for e in events]
        (d / "events.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_code(self, conv_id: str, events: list[ConversationEvent]) -> None:
        """Write generated code as .tsx file."""
        d = self._conv_dir(conv_id)
        if d is None:
            return
        version = sum(
            1 for e in events
            if e.type in ("generation", "growth") and e.status == "success"
        )
        d.mkdir(parents=True, exist_ok=True)
        code = ""
        for e in events:
            if e.type in ("generation", "growth") and e.status == "success" and e.code:
                code = e.code
        if code:
            (d / f"v{version}.tsx").write_text(code, encoding="utf-8")

    def _migrate_flat_layout(self) -> None:
        """Auto-migrate from old flat layout to per-user layout.

        Old layout had a single conversations.json at root and conv dirs
        directly under data_dir. This moves them into user subdirectories.
        """
        old_index = self._dir / "conversations.json"
        if not old_index.exists():
            return

        try:
            data = json.loads(old_index.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return

        if not data:
            old_index.unlink(missing_ok=True)
            return

        import shutil

        for item in data:
            conv = ConversationData(**item)
            user_id = conv.user_id or "anonymous"
            user_convs = self._get_user_index(user_id)

            if conv.id in user_convs:
                continue

            # Move conversation directory
            old_conv_dir = self._dir / conv.id
            new_conv_dir = self._user_dir(user_id) / conv.id
            if old_conv_dir.exists() and not new_conv_dir.exists():
                shutil.move(str(old_conv_dir), str(new_conv_dir))

            user_convs[conv.id] = conv
            self._conv_to_user[conv.id] = user_id

        # Save per-user indexes
        migrated_users: set[str] = set()
        for item in data:
            user_id = item.get("user_id") or "anonymous"
            migrated_users.add(user_id)
        for uid in migrated_users:
            self._save_user_index(uid)

        # Remove old flat index
        old_index.unlink(missing_ok=True)
