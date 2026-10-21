# Shared Context — Plan (v0.2, evidence-derived)

Working title. Codename candidates: `commons`, `lore`, `ctxd`. Naming is open (§10).

**v0.2 change:** the objective is restated as **team throughput**, not token spend, and the design is re-derived from gathered evidence. The full derivation lives in [`docs/design/00-team-speed-model.md`](docs/design/00-team-speed-model.md); every claim below traces to a source in [`docs/inspiration/`](docs/inspiration/README.md).

## 1. Thesis

Engineers and their agents lose time at every boundary: repo, service, team, timezone, branch, session, agent. Each boundary strips context, and the next actor must rebuild it — Savkin counted **seven explanations for one change** across four repos. Our tooling records the lower layer (code, commits, CI) but not the upper layer (intent, decisions, rejected options, discovered constraints). Malcolm's line is the whole problem: **"Git records the code and not human intent."**

The objective is **team throughput**:

> The unit of value is a **landed handoff**: the next actor — human or agent — reaches productive continuation without asking the originator.

Token spend is a **cost-efficiency constraint, not the goal**. Optimizing tokens directly can reduce team speed (trimmed context → wrong-context rework), so the economics metric is cost per merged change. If a change improves tokens but worsens handoff, review, or rework, it is rejected.

### 1.1 The system model (replaces the v0.1 "three tiers")

| Layer | Question it answers | Where it comes from | Freshness |
|---|---|---|---|
| **Lower graph** — repos, packages, API producer/consumer edges, entry points, commands | What exists? | Code itself, deterministic indexer | Commit-pinned, always current |
| **Upper graph** — episodes: sessions, intents, decisions, rejected options, dead ends, traces, PR/CI links | How did it come to be? | Hooks capture sessions; humans author | History is fixed; conclusions must be re-verified |
| **Derivations** — distilled notes (constraints, gotchas, precedent) | What did we learn? | Distilled from episodes | **Guilty until verified against code** |
| **Live state** — in-flight branches, PRs, who is touching what | What is happening now? | Git/CI connectors | Real-time, never stored |

**"Docs rot. Code does not."** — Savkin. Code is the only artifact that is current by definition; every memory is a map, and the map is not the territory. **The most important capability is therefore not recall but materialization:** pull down the actual state of a session, spin it up, and look at ground truth. A stale fact "does not degrade gracefully — it sends the agent down the wrong path with full confidence."

Three consequences drive the design:
1. **Episodic-first, semantic-later.** Capture the session recording; defer distilled digests. Savkin ships episodic-first on purpose.
2. **Verification-first.** Derivations are guilty until code anchors confirm them; episodes are history and are re-materialized before acting.
3. **Precedent, not policy.** Institutional memory is "a negotiated fiction" — we surface episodes that did a thing well; we never author the team's standards.

### 1.2 Origin story: the talk that frames this

Inspiration: Kay Malcolm (Oracle), *"No Memory, No Harness: Why the Database Is the Last Line of Defense"* — annotated transcript in [`docs/inspiration/`](docs/inspiration/no-memory-no-harness-kay-malcolm.md).

Her scenario is the pitch: a team split EMEA/US. At 4am the Netherlands team checks in code, but not the Codex context that produced it. The US team wakes up to a diff with no rationale and re-derives everything.

Ideas adopted directly: the **memory broker** (capture automatically, tag context with the **fork/branch/commit** it belongs to, share team-wide while "developers remain in control"); the memory taxonomy; and **one store, one source of truth** (she demonstrates the failure of splitting memory across relational + document + graph + vector stores with four volunteers and the sentence "the cow jumped over the moon") — validating our Postgres-only decision.

The governance argument for open source: quoting Harrison Chase, **"if you don't own your harness, you don't own your memory."** On file-based memory: it "works with one, but when you scale past one it creates a problem." **Vendor-neutrality is a project value.**

## 2. Goals / non-goals

**Goals**
- Reduce handoff latency, re-explanation count, review latency, rework, and orientation time (definitions: design doc §1).
- Episode capture + materialization so work is resumable by another person *or another agent*.
- Cross-repo reach (space) and session history (time) — attacking only one leaves the bottleneck.
- Works at three sharing levels: solo, team, org. Multi-tenant, self-hostable, one `docker compose`.
- Harness-agnostic: MCP first, hooks for lifecycle moments, CLI/HTTP for everything else.
- Audit, attribution, deletion, and portability. No black box, no proprietary blob.

**Non-goals (v1)**
- Prompt assembly, compaction policy, or anything the harness owns (see §4.0).
- Being an authority on team conventions or standards; being a wiki/notes app.
- A meta-harness that orchestrates multi-repo edits and CI (Polygraph does that; we supply the open memory layer it and others can consume).
- Auto-resolving contradictory memories.
- Hosted SaaS until the protocol and data model stabilize.

## 3. Prior art and the gap

| Project | What it does | Gap for us |
|---|---|---|
| mem0 / OpenMemory | general memory layer, MCP, local-first | single-user oriented; no staleness model; no episodic/materialization |
| Graphiti (Zep) | temporal knowledge graph, `group_id` namespacing | graph-of-facts, assistant-oriented, no code layer |
| Basic Memory | markdown files + MCP | human-authored notes only; no capture, no verification |
| Cipher (Byterover) | OSS memory for coding agents via MCP | per-user; no repo namespaces, no episodes |
| Aider repo-map, repomix, claude-context | code indexing | lower graph only; recomputed per user; no intent |
| OpenAI in-house data agent (Jan 2026) | six-layer context, correctness memory, continuous evals | internal-only; data domain, not shared code context |
| Letta / LangChain Deep Agents | harness-owned memory, open, BYO Postgres | orthogonal: they own *working* memory, we own *durable shared* memory (§4.0) |
| **Nx Polygraph** (Savkin) | agent-agnostic meta-harness; episodic-by-code, session graph, materialize-and-resume, CI as one vector | **closest design to ours, and commercial/closed.** Validates episodic-first; leaves the open, harness-agnostic, cross-org layer unbuilt |
| Oracle AI Database + agent memory SDK | memory broker across forks/branches/commits | closed, Oracle-only |

**The gap:** nobody ships the open, vendor-neutral, **episodic-first shared memory layer** with materialization, verification, and cross-repo reach. Every building block exists; the assembly does not, and the two closest attempts are proprietary.

## 4. Core design

### 4.0 Boundary: working memory vs. shared memory

The strongest published critique of "memory as a service" is that memory is not a plugin — it's the harness, because the harness decides what survives compaction and what the agent sees turn-by-turn. If we claim to *be* an agent's memory, that critique is correct and we lose.

| Owner | Memory | Examples |
|---|---|---|
| **Harness** | Working memory | context window, prompt assembly, compaction, skill metadata, system instructions |
| **Our broker** | Durable shared memory | episodes, derivations, structural index, materialization manifests |

We never control prompt assembly or compaction. We return a token-budgeted, provenance-tagged, freshness-scored pack and let the harness decide. Two obligations:

1. **Hook the lifecycle.** `PreCompact` is the single most valuable integration point — it captures context at the exact moment the harness destroys it. MCP is the API; hooks are the heartbeat.
2. **Portability is a feature.** Every artifact is human-readable, harness-neutral, leave-taking-able: `.context/` markdown, `AGENTS.md`-compatible summaries, plain JSON. Never an encrypted blob. If a team leaves, they keep memory any harness can use.

### 4.1 Data model (the durable contribution)

```ts
Episode {                                   // PRIMARY AGGREGATE — the transferable unit
  id, namespace, title, intent
  repos:      [{ repo, base_sha, head_sha, branch, fork }]
  participants: [{ user|agent, model, harness }]
  traces:     { transcript_ref?, tool_calls_ref?, compaction_snapshots[] }
  decisions:  [{ what, why, options_rejected[] }]
  dead_ends:  [{ tried, outcome, evidence_ref }]
  links:      { prs[], ci_runs[], issues[] }
  materialization: { worktree_spec, setup_commands[], priming_prompt }
  acl:        inherited from every repo/artifact referenced
  status:     "open" | "handed_off" | "reviewed" | "closed" | "resumed_by"
  usage:      { resumed_by[], materialized_count, cited_by_episodes[] }
}

Derivation {                                // distilled note — GUILTY UNTIL VERIFIED
  id, namespace, kind: "constraint" | "gotcha" | "precedent" | "decision" | "fact"
  body_md, est_tokens
  sources:    episode_ids[]                  // never orphaned
  anchors:    [{ path, content_hash, symbol?, commit_sha }]
  verification: { verified_at, verified_against_sha, method: "code_check" | "human" | "test"}
  trust:      "unverified" | "verified" | "disputed" | "superseded"
  validity:   { ttl?, status: "active" | "stale" | "disputed" | "archived" }
  usage:      { retrievals, cites, unique_users, prevented_repeats }
}

IndexEntry {                                // lower graph, commit-pinned, no LLM
  repo, commit_sha, packages[], api_producers[], api_consumers[],
  entry_points[], commands: { build, test, lint, run }, deps[]
}
```

**Three graphs** (Savkin) replace a flat bag of facts:
- **Session graph** — episodes as nodes; edges from shared repos, description/log/commit similarity, participant overlap, code-change similarity, and **time**.
- **Repository graph** — repos as nodes; dependency and API producer/consumer edges.
- **Code-change graph** — similarity of actual diffs.

The repo graph shapes the session graph (sessions touching the same repos are more likely related). Retrieval gets "locality without being trapped by it."

### 4.2 Capture — episode-first

Ordered by value:

1. **`PreCompact` snapshot** — capture the transcript at the moment the harness destroys context. Highest-value hook in the product.
2. **`Stop`/`SessionEnd` episode assembly** — build/update the episode record: intent, repos@SHA, branch, decisions, dead ends, traces. Cheap model, structured JSON. Skip no-op sessions.
3. **Explicit `remember`** — agent proposes, **human confirms** (OpenAI's agent prompts to save; silent capture trains distrust). Writes a derivation linked to the current episode.
4. **Deterministic indexer** — CI/pre-push: tree-sitter + manifests → `IndexEntry`. No LLM.

Quality gate on derivations: schema → dedup → secret/PII scan → "would another engineer find this useful?" → anchor verification. Target **correctness-critical deltas** (the thing that prevented a wrong answer), not session summaries. Reject junk; the #1 killer of this category is an uncurated store agents learn to ignore.

**Note on transcripts:** availability varies by harness (some encrypt or omit compaction summaries). Degrade gracefully: episode shell (intent, repos@SHA, decisions, links) is always capturable; traces are best-effort. The episode record must be useful without the full transcript.

### 4.3 Retrieval — push and pull

**Push:** at `SessionStart`, a budgeted pack (~4k tokens):
- **Orientation header** (~300 tok): repo map, stack, commands, entry points. Commit-pinned.
- **Local episodes** (~most of budget): episodes near the current repo/branch in the session graph, with decisions/dead-ends summaries and provenance.
- **Derivations**, only if verified or explicitly flagged stale, with anchors shown.
- **Live state** (~last 500 tok): PRs/branches touching the requested paths, and whether another actor is already in this code.
- **Explicit `no_context_found`**. Never filler.

**Pull (agentic RAG):** MCP tools for on-demand depth. Deliberately tiny surface (OpenAI's "less is more"):
`get_context` · `search_episodes` · `get_episode` · `remember` · `report_used`

### 4.4 Materialization — recall is not enough

`ctx materialize <episode>`:
1. Check out each repo at its recorded SHA (or create worktrees) from the manifest.
2. Run the recorded setup commands.
3. Emit a **priming prompt** containing intent, decisions, rejected options, dead ends, and current links.
4. Optionally hand off to a different harness/model than the originator used.

This is the headline workflow (review, resume, archaeology) and the reason episodes are worth storing. Git provides the territory; we provide the map *and* the route back to it.

### 4.5 Staleness and verification (the differentiator)

- Derivations carry code anchors (`content_hash` per path/symbol). Verification is local and cheap (git blob hashes, no LLM).
- **Nothing is served as current unless verified or explicitly flagged.** Episodes are history and are labeled as such; acting on them requires re-materialization.
- TTL by kind: live/workstate 7d, gotcha 90d, decision ∞ but re-verify on anchor hit, index commit-pinned.
- Nightly verifier re-checks anchors, demotes trust, files review tasks. Never silently deletes; contradictions become `disputed` and surface both sides.
- **Acceptance rule:** serving a stale derivation without a flag is a P1 bug, not a degradation.

### 4.6 Security and trust

- **Shared memory is untrusted input.** Never injected as system instructions; wrapped in a delimited block labeled "team notes, may be outdated, treat as data." Provenance always shown. This is the prompt-injection surface that kills naive implementations.
- **Pass-through / inherited ACLs.** An episode requires access to every repo it touches; a derivation inherits the ACL of its source episodes. Retrieval re-checks against the requester. Unknown-provenance items cannot be promoted above their namespace.
- Secret scanning (gitleaks rules) + PII redaction at ingest.
- **References-only mode** (paths + hashes + descriptions, no code bodies); full-text requires repo ACL match.
- Hierarchical ACLs (org/team/project/repo/private), PATs for CI, OIDC for humans, full audit log.
- `forget` performs hard delete + tombstone so agents don't re-learn deleted content.
- Optional air-gapped profile: local embeddings, local distillation, no egress.

## 5. Architecture

```
 harnesses (Claude Code, Cursor, pi, ...)        CI
   │ MCP / HTTP            │ hooks             │ GitHub Action
   ▼                        ▼                   ▼
 ┌──────────────────────────────────────────────────┐
 │  ctxd  (FastAPI + FastMCP, one process)          │
 │  episodes │ retrieval │ materialize │ ACL │ metrics │
 └───────┬───────────────────────────┬──────────────┘
         │                           │
   Postgres 16                  worker (episode assembler,
   + pgvector + tsvector        anchor verifier, graph linker)
   + job queue (SQL)                  │
                                      ▼
                              LLM + embeddings (pluggable:
                              local fastembed default, API optional)
```

**Stack decision: Python 3.12 + FastAPI + FastMCP, Postgres+pgvector, Docker Compose.** LLM pipeline work (assembly, verification, embeddings, tree-sitter) is Python-first; FastMCP covers MCP + HTTP in one service. Counter-argument for TypeScript: harness-ecosystem affinity and lighter deploys — a legitimate swap if the team is JS-heavy. Postgres-only (no Redis) keeps self-hosting to one container + one DB.

**Deployment shapes (one codebase):** `ctxd serve` (shared team/org server) · `ctx sync` (export/import reviewed markdown in `.context/`, works with zero server) · single-user local mode (SQLite) for evaluation.

**Distribution:** `uvx shared-context` / `npx` shim / `docker compose up` / Helm later. Friction decides adoption.

```
shared-context/
├── server/            # ctxd: API, MCP, retrieval, ACL
├── cli/               # ctx: login, materialize, get, remember, review, sync, export
├── indexer/           # tree-sitter structural index (lower graph)
├── integrations/
│   ├── claude-code/   # hooks + settings template + skill
│   ├── cursor/  ├── zed/  ├── github-action/
├── web/               # review/curation UI (phase 3)
├── deploy/            # docker-compose.yml, helm/
└── docs/
```

## 6. Harness integration

| Harness | Retrieve | Capture | Materialize |
|---|---|---|---|
| Claude Code | MCP + `SessionStart` pack | `PreCompact` snapshot, `Stop`/`SessionEnd` assembly, `AGENTS.md` instruction block | `ctx materialize` → worktree + priming prompt |
| Cursor / Windsurf / Zed | HTTP MCP config | rule file prompts `remember`; transcript capture where API allows | same CLI path |
| Codex / aider / others | `ctx run <harness>` wrapper writes the pack to a file | wrapper captures session log if available | same CLI path |
| Any CI | — | index refresh + PR check: "this diff touches paths with unverified derivations / active overlapping episodes" | — |

Transport detail: many harnesses can't send auth headers to HTTP MCP, so ship a tiny **stdio↔HTTP bridge** (`ctx mcp-bridge`) reading the token from keychain/env. Integration must take 2 minutes, not 2 hours.

## 7. Roadmap

**Phase 0 — recorder + observe (2 weeks)**
Build only the capture spine: episode recorder + a standalone store + the event log. Runs in **observe-only mode** on the pilot team — capture, no injection, no retrieval features.
- H1 is tested on first-party events: orientation time (session start → first edit), re-derivation rate (same files/commands across sessions and users), re-explanation signals (restatement prompts), overlap between open episodes.
- **H1 gate:** if context reconstruction is a small share of engineering time, stop and re-derive.
- Every metric baseline recorded here becomes the counterfactual for Phase 1. No external logs, no time-diary surveys.
Deliverable: a working recorder plus the numbers — not a slide deck.

**Status: BUILT** (commit `2cb6f7e`). Server ingest + CLI + Claude Code hooks + local analyzer + report; 10 unit tests and a 16-check end-to-end smoke test. Runbook and decision gates: [`docs/PHASE0.md`](docs/PHASE0.md). Remaining requirement: a pilot repo and 2+ engineers.

**Phase 1 — MVP (4 weeks)**
C1 Episode capture + C2 Materialization + C3 Structural index for one repo/stack · Postgres (episodes, derivations, index) · Claude Code hooks · CLI (`login/materialize/get/remember/index/export`) · ACL inheritance · tiny MCP surface · docker-compose · baseline metrics report · eval sets in CI.

**Phase 2 — team-grade (4 weeks)**
C4 Why-is-this-here (commit/line → episode) · C5 verified derivations · C6 overlap detection + cross-repo CI vector · C7 expert routing · session/repo graph v1 · review queue · git export with PR review · nightly verifier · multi-harness.

**Phase 3 — org-grade**
C8 richer graph retrieval · cross-repo sessions · review web UI · federation and promotion (private → team → org) · conflict/supersede workflows · Helm/K8s · air-gapped profile.

## 8. Metrics (build in from day one)

**Primary — team throughput** (definitions in design doc §1): handoff latency · re-explanation count · review latency (availability-adjusted) · rework rate · orientation time · duplicate-work rate · self-service rate.

**Secondary — economics:** tokens per merged change · reuse rate · distillation cost per accepted item. Honest caveat: avoided tokens can only be *estimated*; use a controlled toggle cohort and report confidence intervals. Never ship a fake savings number.

**Evals as infrastructure from Phase 0:** curated question/expected-context pairs per pilot repo, scored semantically with explanations, run in CI on every retrieval or distillation change. Without them, "the store got better" is an opinion and regressions are invisible until an agent confidently repeats a stale claim.

**First-party measurement (design directive).** Every metric is computed from events the solution itself emits — episode lifecycle, handoffs, materializations, retrievals, citations, rework links. We do **not** import third-party session logs or rely on surveys. Rationale: we control the semantics, consent is inherent in tool use, log formats can't break under us, and the same data powers the product's own evals. Third-party transcript parsing was a feasibility probe, not a data source.

**Observe-only mode bootstraps the baseline.** The recorder ships first and runs in capture-only mode (no injection) for a baseline window; then injection is enabled and the delta is measured on the same users, repos, and work — a clean counterfactual with zero external data.

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Stale context misleads confidently** — worse than no context | **Critical** | verification-first serving rule; anchors; explicit stale flags; materialization escape hatch; acceptance rule in §4.5 |
| Junk store → agents ignore it → death spiral | **Critical** | write gates, confirm-to-store, derivation-last ordering, quality metrics |
| Prompt injection via shared memory | **Critical** | memory is data, never instructions; delimited blocks; provenance; secret scan; review for org-visible items |
| Capture friction / transcript unavailability | High | episode shell is useful without traces; degrade gracefully; H4 measures policy reality; manual fallback |
| Secret/customer data leakage | High | ingest scanning, references-only default for org visibility, inherited ACLs, timestamps, `forget` + tombstone |
| Scope creep into meta-harness / orchestration | High | §2 non-goals; we supply the layer, not the orchestrator |
| Cost inversion (assembly costs more than saved) | High | assemble only delta sessions, cheap/local models, batch, measure ROI weekly |
| Adoption friction | High | 2-minute install, zero-config defaults, serverless markdown mode |
| Retrieval noise | Medium | trust gating, strict budgets, explicit "no context found", `report_used` feedback, small tool surface |
| Many-harness maintenance burden | Medium | MCP as the only hard dependency; integrations as thin shims |
| Legal/compliance | Medium | refs-only mode, per-repo encryption option, air-gapped profile, audit log |

## 10. Open questions (need answers before Phase 1)

1. **Pilot teams for Phase 0** — which two teams, and can we instrument them (time study, PR logs, session access)? This is the H1 gate and the top blocker.
2. **Where are the hours actually going?** Do not assume handoffs dominate — measure before building.
3. **Harness mix and hook installability** — what do pilots use, and is installing hooks + a collector acceptable? (Thick integration is required for `PreCompact`.)
4. **Transcript/data policy** — may code bodies, paths, or traces leave a laptop? Drives ACL, embeddings, refs-only mode.
5. **Scale/hosting** — teams, sessions/day, single VM or k8s, air-gapped anywhere?
6. **Tenancy** — recommend single-tenant deploy with namespaces day one, multi-tenant later. Confirm.
7. **License** — recommend Apache-2.0 (adoption > monetization now). AGPL only if a hosted-competitor concern exists.
8. **Name** — `commons`, `lore`, `ctxd`, or something else.

## 11. What makes this worth building

Every team already pays the context tax; they call it "getting up to speed." The blocks exist — MCP, hooks, pgvector, tree-sitter, cheap models — but nobody has assembled them into an **open, episodic-first, verifiable, materializable** shared memory layer. The two closest attempts (Polygraph, Oracle's broker) are proprietary, and the harness vendors are busy locking memory *into* their platforms. The compounding asset is the shared episode graph: the more people contribute, the more context any single agent has — more than any individual carries. Own the format, own the memory, make the team faster.
