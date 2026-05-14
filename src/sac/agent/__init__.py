"""
SaC Builtin — agents that ship in-process with SaC.

Two pieces, deliberately kept separate:

  - `StandaloneAgent` (agent.py) — the real default agent. Sibling-level to
    external agents (OpenClaw, LangGraph, ...). Owns search, formats data,
    drives core via Conversation.ingest. Survives long-term.

  - `LegacyShim` (legacy.py) — transitional adapter for the pre-protocol-pivot
    `send` / `classify` API surface used by sac-web and the MCP server. Goes
    away once those consumers migrate to the dual-channel /inbox flow.
"""

from sac.agent.agent import StandaloneAgent
from sac.agent.legacy import LegacyShim

__all__ = ["StandaloneAgent", "LegacyShim"]
