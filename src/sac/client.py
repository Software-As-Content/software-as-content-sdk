"""
SaC Client — the entry point that wires everything together.
"""

from __future__ import annotations

from sac.conversation import Conversation
from sac.prompts.app import DEFAULT_MODEL
from sac.providers.base import LLMProvider, SearchProvider
from sac.providers.openrouter import OpenRouterProvider
from sac.providers.tavily import TavilyProvider
from sac.store.base import ConversationStore
from sac.store.memory import MemoryStore
from sac.types import App, ConversationData, ConversationSettings


class SaC:
    """
    Software as Content SDK — main entry point.

    Usage:
        sac = SaC(api_key="sk-...")
        app = await sac.generate("2026 travel guide for Hangzhou")

    Multi-turn:
        conv = sac.conversation()
        app = await conv.generate("travel guide", web_search=True)
        app = await conv.evolve("add restaurants")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        search_api_key: str | None = None,
        llm: LLMProvider | None = None,
        search: SearchProvider | None = None,
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

        # Search provider: explicit, or default Tavily if key given
        if search is not None:
            self._search: SearchProvider | None = search
        elif search_api_key:
            self._search = TavilyProvider(search_api_key)
        else:
            self._search = None

        # Store: explicit or default in-memory
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
            search=self._search,
            store=self._store,
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
