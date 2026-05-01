# Pattern: Internal Ops Agent

> 🚧 **Stub** — describes the intended example. Code coming soon.

## When this pattern fits

You're building an internal tool — for support, ops, finance, customer
success — where an employee asks the agent something ("show me at-risk
customers this week", "summarize last night's deploy failures") and then
needs to *act* on the result, not just read it.

## Why SaC fits

- Internal-tool UI work is the most expensive form of frontend engineering
  per amount of value delivered. Every team has a queue of "we should build
  a dashboard for X" requests that never get prioritized. SaC turns those
  into agent-generated UIs on demand.
- The user is a known authenticated employee — you can wire `__sac_action`
  buttons to call your real internal APIs (file a ticket, mark resolved,
  escalate).
- Persistence per-user (via `FileStore` keyed on employee id) lets each
  person have their own working set of saved views.

## What this example will show

1. An agent with internal tools (Postgres query, ticketing API, alert
   feed) that surfaces state via SaC instead of canned dashboards.
2. Wiring affordance buttons to backend mutations through a thin
   action-router on top of `__sac_action`.
3. Multi-tenant patterns — separating conversation stores per team, plus
   shareable views via the hosted `sac.dynsoft.ai/share/...` flow.

## Frameworks that map cleanly

Custom internal agent loops, LangGraph-based ops bots, MCP-mediated agents
running inside an internal Claude Desktop / Cursor workspace.

## Don't use this pattern for

- Customer-facing production interfaces (use SaC outputs as inspiration,
  build the real UI properly).
- Compliance-critical workflows where every UI element needs to be reviewed.
