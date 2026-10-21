# Inside OpenAI's in-house data agent — distilled notes

**Source:** OpenAI, *Inside OpenAI's in-house data agent*, published Jan 29 2026.
<https://openai.com/index/inside-our-in-house-data-agent/> (Cloudflare-blocked to plain curl; retrieved via text proxy.)

An internal tool, not a product — but it's the most detailed public account of *layered context done well at scale*, and it's about data agents, not coding agents, so it's an outside-in validation of our tier model.

## Scale and problem (context for why layering is needed)

- 3.5k internal users, 600+ PB, 70k datasets. Finding the right table was the most time-consuming part of analysis.
- Without context, "even strong models produce wrong results, such as vastly misestimating user counts or misinterpreting internal terminology."
- Available through Slack, web, IDE, **Codex CLI via MCP**, and ChatGPT MCP connector. Note: MCP as the distribution surface, exactly our strategy.

## The six context layers

| Layer | What it is | Our equivalent |
|---|---|---|
| 1. Table usage | schema metadata, lineage, historical query inference | structural index (tier 1) |
| 2. Human annotations | domain-expert descriptions of intent, semantics, caveats "not easily inferred from schemas or past queries" | semantic memory, but **human-authored and high-trust** |
| 3. Codex enrichment | code-level definition of each table, refreshed automatically | structural index derived from code, auto-refreshed |
| 4. Institutional knowledge | Slack, Docs, Notion — launches, incidents, codenames, metric definitions; ingested, embedded, **stored with metadata and permissions**; "retrieval service handles access control and caching at runtime" | live connectors + ACL-filtered retrieval |
| 5. Memory | corrections and nuances saved for next time | semantic memory (see below) |
| 6. Runtime context | live queries when prior context is stale or missing | live tier — query at request time, never store |

Layer 6 is worth internalizing: **when context is stale, the agent queries the source of truth live.** Our staleness design has the same escape hatch — flag stale, offer to re-derive, don't pretend.

## Layer 5 (memory) — the most directly transferable section

- Goal: "retain and reuse **non-obvious corrections, filters, and constraints that are critical for data correctness but difficult to infer** from the other layers alone."
  → Our distillation gate should target **correctness-critical deltas**, not session summaries. A summary of what happened is low-value; a correction that prevents a wrong answer is high-value.
- The example: matching an experiment gate by string was wrong; memory was needed "to ensure it was able to filter correctly, instead of fuzzily trying to string match."
- **Save is confirmed, not silent:** "it will prompt you to save that memory for next time." Memories are also manually creatable and editable.
  → Design implication: the agent proposes, the human disposes. Silent auto-capture trains people to distrust the store.
- **Scope: global and personal.** Matches our org/team/repo/private namespaces exactly.

## Security model

- "All of the agent's access is strictly **pass-through**, meaning users can only query tables they already have permission to access."
- It exposes reasoning, assumptions, execution steps, and links to underlying results for verification.

→ Design implication we hadn't fully specified: **memory items must inherit the ACL of their derivation sources, and retrieval must re-check against the requester.** A note derived from a private repo or a restricted dataset cannot become org-visible just because it was distilled. Namespace ACLs alone are insufficient; we need source-inherited ACLs plus an "unknown provenance" flag.

## Evals: "unit tests that run continuously"

- Curated question/answer pairs, each with a manually authored "golden" answer.
- **Not naive string matching** — generated output can differ syntactically and still be correct; they compare both the artifact and the resulting data, fed to a grader that returns a score + explanation.
- Run continuously as canaries to catch regressions.

→ We adopt this for both retrieval quality and distillation quality. Without evals, "the store got better this week" is an opinion. See PLAN §8.

## Three lessons learned

1. **Less is more** — exposing the full tool set caused confusion from overlapping functionality; they consolidated and restricted tools.
   → Our MCP surface must stay small and unambiguous. Resist adding `get_similar_context`, `find_notes_by_tag`, etc. One good `get_context`, one `search`, one write path.
2. **Guide the goal, not the path** — prescriptive prompting degraded results; higher-level guidance let the model choose its execution path.
3. **Meaning lives in code** — "Schemas and query history describe a table's shape and usage, but its true meaning lives in the code that produces it." Pipeline logic captures assumptions, freshness guarantees, and business intent that never surface in SQL or metadata.

→ Lesson 3 is the structural-index argument, stated better than we had it: the index isn't just "where things are," it's the *intent-bearing artifact* that only code can provide. It's also why a pure vector store over docs is insufficient.

## What does not transfer

This is a **data** agent. Queries are read-only, correctness is verifiable against golden SQL, and the failure mode is a wrong number. Coding agents mutate code, correctness is fuzzier, and the handoff unit is a branch/fork rather than a table. Our capture/merge/conflict logic will be harder than theirs — budget for it.
