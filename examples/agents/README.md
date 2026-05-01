# Agent Integration Patterns

The SaC SDK is **pattern-based**, not framework-based. Rather than maintain a
separate quickstart for every agent framework (LangGraph, CrewAI, Mastra,
Claude Agent SDK, custom loops, …), we organize examples by the *kind of
agent* you're building.

If your agent owns its frontend and produces outputs that benefit from user
interaction, one of these patterns probably matches you. Pick the closest
pattern, copy the structure, and adapt to your framework.

## The four archetypes

| Pattern | When this is you | Status |
|---|---|---|
| [`personal-assistant/`](./personal-assistant/) | Agent that talks to one end-user, multi-channel (chat, voice, calendar, etc) | 🚧 stub |
| [`research-agent/`](./research-agent/) | Agent that explores a topic and produces structured findings the user wants to drill into | 🚧 stub |
| [`data-analysis-agent/`](./data-analysis-agent/) | Agent that processes data and produces interactive visualizations and breakdowns | 🚧 stub |
| [`internal-ops-agent/`](./internal-ops-agent/) | Internal-tool agent that surfaces operational state and lets users act on it | 🚧 stub |

Each subdirectory is currently a **README stub** describing what the example
will look like. **Working code lands as we (and the community) build the first
real integrations.** PRs welcome.

## What's NOT here, intentionally

- A "LangGraph quickstart" or "CrewAI quickstart" — frameworks come and go;
  patterns are durable. The pattern README will mention which frameworks fit
  naturally.
- A template for **chatbots that mostly answer in text** — those don't need
  SaC. See the README's "When NOT to use SaC" section.
- A template for **closed-platform agents** (Salesforce Agentforce, Copilot
  Studio, etc) — you can't embed a renderer there, only link out.
