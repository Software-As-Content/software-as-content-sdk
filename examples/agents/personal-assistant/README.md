# Pattern: Personal Assistant

> 🚧 **Stub** — describes the intended example. Code coming soon.

## When this pattern fits

You're building an agent that talks to one end-user across channels (chat,
voice, calendar, etc). The agent is general-purpose; today it answers in
text, but you want richer responses for the cases where text falls short —
"what's on my week", "compare these three options", "show me my spending".

## Why SaC fits

- Most personal-assistant questions have an **exploration shape** — the user
  doesn't know exactly what they want until they see it. SaC's evolve loop
  is designed for this.
- The agent already owns the user's UI surface (web chat, embedded panel),
  so dropping in a SaC renderer is straightforward.
- Multi-channel voice/text inputs feed naturally into `Conversation.send` and
  `Conversation.evolve`.

## What this example will show

1. A small agent loop that decides "should I respond with text, or with an
   app?" and routes to either a chat reply or `sac.generate` / `sac.evolve`.
2. Hooking up a structured affordance (Φs) — a button in the rendered app
   that triggers the agent's next action via the existing `__sac_action`
   bridge.
3. Persisting per-user conversation state via `FileStore` keyed on user id.

## Frameworks that map cleanly

OpenClaw (planned reference integration), any custom Python agent loop,
LangGraph nodes that emit structured responses.

## Don't use this pattern for

- Agents whose 95% output is short conversational text (no SaC needed).
- Agents that live entirely in channels that can't render rich UI (SMS, plain
  WhatsApp). For those, link out to `sac.dynsoft.ai/share/...`.
