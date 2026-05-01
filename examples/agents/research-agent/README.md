# Pattern: Research Agent

> 🚧 **Stub** — describes the intended example. Code coming soon.

## When this pattern fits

Your agent investigates a topic, gathers sources, and produces a report. The
user then wants to drill in — filter by date, compare sources, expand a
specific claim, pivot the angle. Plain markdown output makes this awkward;
SaC produces output that's actually navigable.

## Why SaC fits

- Research output is **multi-dimensional** — sources, claims, timestamps,
  confidence — and benefits from real layout, not flat prose.
- The user's exploration is iterative. Every "expand this", "show me more
  on X", "compare with Y" is a natural `evolve` call.
- `sac.generate(intent, web_search=True)` already integrates Tavily for
  retrieval, so the SaC engine can do the research + render in one call —
  or you can hand it pre-fetched data via custom prompts.

## What this example will show

1. An agent that takes a topic, fans out searches, summarizes findings, and
   hands the structured result to SaC for rendering.
2. Evolve patterns specific to research: "expand this section", "swap
   sources", "rerank by date", "export as report".
3. Citation propagation — making sure rendered apps preserve source links
   from the underlying search results.

## Frameworks that map cleanly

Anthropic Claude Agent SDK research loops, custom retrieval-augmented agent
loops, multi-step planners (LangGraph / CrewAI).

## Don't use this pattern for

- One-shot factual lookups ("what's the capital of France"). Plain text wins.
- Conversational Q&A where the user just wants the answer, not to explore it.
