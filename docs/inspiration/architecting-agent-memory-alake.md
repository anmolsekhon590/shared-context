# Architecting Agent Memory — distilled notes

**Source:** Richmond Alake (MongoDB), *Architecting Agent Memory: Principles, Patterns, and Best Practices*, AI Engineer. Talk page: <https://ai.engineer/talks/architecting-agent-memory-principles-patterns-and-best-practices>.

Vendor talk (MongoDB), but it contains two architectural distinctions worth adopting.

## 1. "Agent memory is persistent state that can inform a later execution step"

Not *any* stored information — memory is defined by its use. "Storage alone is therefore insufficient: the application needs a **memory-management system** that organizes what enters the model's context window." A large context window is not a reason to insert the whole database; "selection and structure determine whether retained information helps produce a relevant response."

Lifecycle: **generation → storage → retrieval → integration → update → deletion**, plus explicit *forgetting*. He argues for negative retention signals (which experiences remain salient), not just tombstone rows.

## 2. Separate the memory provider from memory management

| Layer | Responsibility |
|---|---|
| **Memory provider** | store records, expose retrieval capabilities |
| **Memory management** | decide what to retain, retrieve, and integrate |

This is the cleanest decomposition for our architecture, and it supports our positioning: our service is **management + protocol**; Postgres is the **provider**. It also means the data model must be explicit about *salience, recency, and provenance* (management signals) rather than assuming storage equals memory.

## 3. Other patterns worth stealing

- **Workflow memory / failed executions.** When a step fails, store the failure and retrieve it during the next attempt to steer away from the dead end. "The adaptation occurs through retrieved context" — no weight updates. This is the mechanical justification for our `gotcha`/dead-end capture: it is the cheapest way to stop a team from repeating an experiment.
- **Agentic RAG.** Expose retrieval as a *tool* and let the agent choose when to pull context, instead of a fixed pre-retrieval step. Our design does both: push a pack at `SessionStart`, expose pull tools for later turns.
- **Toolbox memory.** Don't ship every tool schema in context; retrieve a relevant subset. Sideways-applicable: it's another argument for keeping our MCP tool surface tiny — with only ~4 tools, the whole toolbox fits and the problem disappears.
- **Conversation records need retrieval signals** (timestamps, conversation id, recall recency) — not just content. Embedding-only retrieval is weaker than content + structured signals.

## What we reject

The talk's answer to every question is "MongoDB as provider," and it stays at the pattern level — no measured results. It also leaves the two hardest problems open: **what deserves to be remembered** and **how to detect that a memory is no longer true**. Those are the two problems our design is organized around. Citations: MemGPT (arXiv 2310.08560), Mem0, Zep (arXiv 2501.13956) as *memory management* tools; MongoDB as *provider*.
