"""
SaC SDK — Software as Content

An open-source Python SDK that gives any AI agent the ability to
generate and evolve interactive UI through conversation.
"""

from sac.sac import SaC
from sac.conversation import Conversation
from sac.runtime.providers.base import LLMProvider, SearchProvider
from sac.runtime.store.base import ConversationStore
from sac.runtime.store.file import FileStore
from sac.runtime.store.memory import MemoryStore
from sac.types import (
    App,
    ConversationData,
    ConversationSettings,
    GrowthDecision,
    IntentSuggestion,
    PipelineChunkEvent,
    PipelineCompleteEvent,
    PipelineErrorEvent,
    PipelineEvent,
    PipelineSearchEvent,
    PipelineStageEvent,
    SearchResult,
)

__all__ = [
    # Core
    "SaC",
    "Conversation",
    "App",
    # Config
    "ConversationSettings",
    "ConversationData",
    # Types
    "SearchResult",
    "IntentSuggestion",
    "GrowthDecision",
    # Events
    "PipelineEvent",
    "PipelineStageEvent",
    "PipelineSearchEvent",
    "PipelineChunkEvent",
    "PipelineCompleteEvent",
    "PipelineErrorEvent",
    # Protocols
    "LLMProvider",
    "SearchProvider",
    "ConversationStore",
    # Store implementations
    "MemoryStore",
    "FileStore",
]

__version__ = "0.1.0"
