# Pattern: Data Analysis Agent

> 🚧 **Stub** — describes the intended example. Code coming soon.

## When this pattern fits

The user has data (a CSV, a query result, an API response) and wants to
understand it. Your agent inspects, summarizes, suggests breakdowns — and
the user wants to slice it: "group by region", "show only Q3", "what's
driving this spike", "switch to a stacked bar".

## Why SaC fits

- Data analysis is **inherently exploratory** — the user discovers what they
  want to see by interacting with the first view.
- Charts and tables are SaC's bread and butter (recharts is in the default
  renderer). The agent doesn't need to commit to one chart type up front.
- Each "slice it differently" is a clean `evolve` call. SaC's growth_decision
  often picks `extend_current` (preserving the data context) rather than
  rebuilding from scratch.

## What this example will show

1. An agent that takes a data source (CSV, dataframe, query) and generates an
   initial dashboard via `sac.generate`.
2. Specialized evolve prompts for data work — adding filters, switching
   visualizations, computing derived columns.
3. Custom design-system extension if you need branded charts.
4. Embedding the resulting app inline in a Jupyter notebook (an underrated
   integration).

## Frameworks that map cleanly

Pandas + agent loop, Anthropic Claude with tool use over data tools, custom
analytics pipelines.

## Don't use this pattern for

- Production dashboards consumed by many users (build a proper BI tool).
- Real-time streaming data with strict refresh requirements.
