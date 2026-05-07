"""
SaC Client — the entry point that wires everything together.
"""

from __future__ import annotations

from pathlib import Path

from sac.builtin.agent import BundledAgent
from sac.conversation import Conversation
from sac.runtime.producer import CodeProducer, DefaultCodeProducer
from sac.runtime.prompts.app import DEFAULT_MODEL
from sac.runtime.providers.base import LLMProvider, SearchProvider
from sac.runtime.providers.openrouter import OpenRouterProvider
from sac.runtime.providers.tavily import TavilyProvider
from sac.runtime.store.base import ConversationStore
from sac.runtime.store.file import FileStore
from sac.runtime.store.memory import MemoryStore
from sac.types import App, ConversationData, ConversationSettings


class SaC:
    """
    Software as Content SDK — main entry point.

    Usage:
        sac = SaC(api_key="sk-...")
        app = await sac.generate("2026 travel guide for Hangzhou")

    Store options (pick one):
        sac = SaC(api_key="...", store=MemoryStore())          # in-memory, no persistence
        sac = SaC(api_key="...", store=FileStore(".sac"))       # JSON files on disk
        sac = SaC(api_key="...", store=your_custom_store)       # any ConversationStore impl
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        search_api_key: str | None = None,
        llm: LLMProvider | None = None,
        search: SearchProvider | None = None,
        producer: CodeProducer | None = None,
        store: ConversationStore | None = None,
        model: str = DEFAULT_MODEL,
        settings: ConversationSettings | None = None,
    ) -> None:
        # LLM provider: explicit or default OpenRouter
        if llm is not None:
            self._llm = llm
        elif api_key:
            self._llm = OpenRouterProvider(api_key)
        else:
            raise ValueError("Either 'api_key' or 'llm' provider must be provided.")

        # Search provider: lives at the agent layer (BundledAgent), not in core.
        # Kept on SaC for backwards-compat constructor signatures and for use
        # by the bundled default agent below.
        if search is not None:
            self._search: SearchProvider | None = search
        elif search_api_key:
            self._search = TavilyProvider(search_api_key)
        else:
            self._search = None

        # Code producer: turns intent + content + prior_app into a new App version.
        # Pure rendering — knows nothing about search.
        self._producer: CodeProducer = producer or DefaultCodeProducer(self._llm)

        # Bundled default agent — sibling to external agents (OpenClaw, etc.).
        # Owns search execution, intent suggestions, classify. Drives core
        # via Conversation.ingest. One per SaC; shared across conversations.
        self._bundled_agent = BundledAgent(self._llm, self._search)

        # Store: explicit, or default MemoryStore (no persistence)
        # Available implementations:
        #   MemoryStore()              — in-memory, data lost on restart
        #   FileStore(data_dir)        — JSON files on disk, persistent
        #   <your own>                 — implement ConversationStore protocol
        self._store: ConversationStore = store or MemoryStore()

        self._model = model
        self._default_settings = settings or ConversationSettings()

    def conversation(
        self,
        id: str | None = None,
        *,
        model: str | None = None,
        settings: ConversationSettings | None = None,
    ) -> Conversation:
        """
        Create a new conversation or prepare to load an existing one.

        Args:
            id: Optional conversation ID. If None, a new conversation is created.
            model: Override the default model for this conversation.
            settings: Override the default settings for this conversation.
        """
        conv_settings = settings or self._default_settings.model_copy()
        conv_model = model or self._model

        data = ConversationData(
            model=conv_model,
            settings=conv_settings,
        )
        if id:
            data.id = id

        # Eagerly create in store (fire-and-forget pattern handled by Conversation)
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._store.create_conversation(data))
        except RuntimeError:
            # No running loop — will be created on first operation
            pass

        return Conversation(
            data=data,
            llm=self._llm,
            producer=self._producer,
            store=self._store,
            bundled_agent=self._bundled_agent,
        )

    async def generate(self, intent: str, **opts: object) -> App:
        """
        Convenience shortcut: create a temporary conversation and generate.

        Equivalent to:
            conv = sac.conversation()
            app = await conv.generate(intent)
        """
        conv = self.conversation()
        return await conv.generate(intent, **opts)

    async def close(self) -> None:
        """Close underlying HTTP clients."""
        if hasattr(self._llm, "close"):
            await self._llm.close()
        if self._search and hasattr(self._search, "close"):
            await self._search.close()
