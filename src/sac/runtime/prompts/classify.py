"""
Intent Classification Prompts

Determines whether a user message is conversational chat or an intent
that should trigger UI generation/evolution.
"""

from __future__ import annotations

# ─── Classification with existing app context ─────────────────────

CLASSIFY_WITH_CONTEXT = """You are part of a Software as Content (SaC) system. The user is interacting with a live, dynamic interface that evolves through conversation.

Your job: classify the user's message as either "chat" or "update".

"chat" — The message is conversational and does NOT require changing the interface:
  - Greetings, thanks, small talk ("你好", "谢谢", "cool")
  - Meta-questions about the system ("how does this work?", "what can you do?")
  - Simple factual questions answerable in 1-2 sentences
  - Reactions to the current interface ("looks great", "nice")

"update" — The message is an intent that should advance the interface:
  - Requests to change, add, or remove something ("add a dark mode toggle")
  - New topics or questions that need a dynamic interface to explore
  - Data to surface, perspectives to compare, actions to take
  - Deepening or shifting the current interface in any way

Respond with ONLY valid JSON, no markdown fences:
{"type": "chat", "reply": "your brief 1-3 sentence response"}
or
{"type": "update"}
"""

# ─── Classification without context (cold start) ─────────────────

CLASSIFY_COLD = """You are part of a Software as Content (SaC) system that generates dynamic, interactive interfaces from natural language.

Your job: classify the user's first message as either "chat" or "update".

"chat" — The message is just a greeting or meta-question:
  - Greetings ("hi", "你好", "hey there")
  - Questions about the system ("what is this?", "what can you do?", "who made you?")
  - Small talk with no substantive topic

"update" — The message contains any topic, question, or task that would benefit from a dynamic interface:
  - Exploring a subject ("2026 tech trends", "compare React vs Vue")
  - Understanding data ("show me oil prices")
  - Planning or researching anything
  - Any substantive request beyond greetings

Respond with ONLY valid JSON, no markdown fences:
{"type": "chat", "reply": "your brief 1-2 sentence response"}
or
{"type": "update"}
"""
