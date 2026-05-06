"""
SaC Builtin Agent

The "default agent" that ships with SaC for standalone use. Sibling-level to
external agents (OpenClaw, LangGraph, Claude Agent SDK, ...): all of them
talk to SaC's pure interaction core via the same protocol contract. This one
just happens to live in the same Python process for convenience.

It owns:
  - search execution (when web_search is enabled)
  - intent suggestion generation
  - chat-vs-update classification (for the standalone web UI's text input)

It does NOT own:
  - rendering decisions (those live in core's renderer / pipelines)
  - protocol routing (those live in core's /inbox + Conversation)
"""

from sac.builtin.agent import BundledAgent

__all__ = ["BundledAgent"]
