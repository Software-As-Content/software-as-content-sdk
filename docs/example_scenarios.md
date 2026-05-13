# Example Scenarios

Where does SaC shine? Here are four common agent scenarios where generating interactive UI on the fly beats plain text output.

> 🚧 These are scenario descriptions — working code examples will land once the SDK API stabilizes.

---

## 1. Personal Assistant

An agent that talks to one user across channels (chat, voice, calendar). Most replies are text, but some questions — "what's on my week", "compare these options", "show me my spending" — deserve a real UI.

SaC lets the agent decide per-turn whether to reply with text or render an interactive view, without building separate frontends for each case.

---

## 2. Research Agent

An agent that investigates a topic, gathers sources, and produces findings. The user then wants to drill in — filter by date, compare sources, expand a section, pivot the angle.

Research output is multi-dimensional (sources, claims, timestamps, confidence). Flat prose makes it hard to navigate. SaC renders structured, explorable output that the user can interact with iteratively.

---

## 3. Data Analysis

The user has data (CSV, query result, API response) and wants to understand it — "group by region", "show only Q3", "what's driving this spike", "switch to a bar chart".

Data analysis is inherently exploratory. The user discovers what they want to see by interacting with the first view. SaC handles charts, tables, and filter controls natively, and each follow-up request updates the existing view.

---

## 4. Internal Ops Tools

An internal agent for support, ops, or finance where an employee asks "show me at-risk customers this week" and then needs to *act* on the result — file a ticket, escalate, mark resolved.

Internal-tool UI is expensive to build per amount of value delivered. SaC generates these UIs on demand, and action buttons can be wired to real backend APIs.

---

## What's NOT a good fit

- **Chatbots that mostly answer in text** — if 95% of output is short conversational replies, you don't need SaC.
- **Production dashboards** consumed by many users with strict requirements — build a proper BI tool.
- **Closed platforms** (Salesforce Agentforce, Copilot Studio) — can't embed a renderer, only link out.
