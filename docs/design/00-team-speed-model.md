# 00 — The Team-Speed Model

**Purpose:** define what we are optimizing, derive it from the gathered evidence rather than from assumptions, and state what the design must therefore do. This document constrains everything downstream (protocol, data model, capture, retrieval).

**Status:** draft for review. Every capability below is traced to a source in `docs/inspiration/`.

---

## 1. What "teams faster" means

The original brief was "reduce token spend across teams." The evidence says that is a *symptom*. Malcolm's framing is the correct objective:

> "AI makes individuals faster. Shared memory makes teams faster."

So the objective is **team throughput**, and tokens become a **cost-efficiency constraint**, not the goal. This distinction matters because optimizing tokens directly can *reduce* team speed: trimming context to save tokens produces wrong-context rework, which costs more engineer-hours than it saves in API spend. The metric that captures both is **cost per merged change**.

### Primary metrics (team throughput — this is what we optimize)

| Metric | Definition | Baseline source |
|---|---|---|
| **Handoff latency** | Time from "work paused / committed / handed off" → next actor's first productive step | Savkin's "seven explanations" |
| **Re-explanation count** | Times the same intent must be restated across people, agents, repos, sessions | Savkin |
| **Review latency (availability-adjusted)** | PR opened → substantive review, split by whether it was blocked waiting on the author | Savkin's review workflow |
| **Rework rate** | Changes corrected/reverted due to wrong assumptions or lost intent (proxy: revert rate, follow-up fix PRs, review-churn commits) | Malcolm testing/validation; OpenAI correctness memory |
| **Orientation time** | Joining a repo/subsystem → first merged change | OpenAI table discovery; Savkin space constraint |
| **Duplicate-work rate** | Two actors unknowingly solving the same problem | Malcolm diverging repos |
| **Self-service rate** | Questions answered without asking a human | Savkin archaeology workflow |

### Secondary metrics (economics — constraints, not objectives)

Tokens per merged change · context reuse rate · distillation cost per accepted item · estimated avoided tokens. Reported honestly with confidence intervals (§8 of PLAN).

**Rule:** if a change improves token metrics but worsens handoff/review/rework metrics, it is rejected. Tokens are the shadow, not the substance.

---

## 2. Evidence: what actually slows teams

| # | Observation | Source | Mechanism | Symptom |
|---|---|---|---|---|
| E1 | Code generation got faster; **coordination did not** | Malcolm | bottleneck moved from implementation to coordination | managers can't explain flat throughput; more token spend, same delivery rate |
| E2 | Overnight handoff delivered files but not reasoning | Malcolm | the artifact survived; the context did not | next timezone re-derives everything |
| E3 | "Git records the code and not human intent" | Malcolm | VCS captures *what exists*, not *how it came to be* | intent reconstructed by archaeology or by asking a human |
| E4 | One change required **seven explanations** across four repos | Savkin | every boundary crossed (repo, session, agent, time) strips context; cost scales with boundary count | developer time and tokens spent restating the same intent |
| E5 | Agents have bounded **space** (one repo) and **time** (one session) | Savkin | repo-sized visibility + session-sized memory | humans carry the graph in their heads; bus factor |
| E6 | Repos diverge; CI results treated independently miss cross-repo failures | Malcolm, Savkin | no shared model of in-flight work | integration failures discovered late |
| E7 | A wrong constraint caused fuzzy string matching instead of the right filter | OpenAI | correctness-critical knowledge is not inferable from structure | wrong answers, then debugging the wrong answer |
| E8 | Recording an episode does **not** mean its conclusions still hold | Savkin | recorded state ≠ current state | confident misdirection |
| E9 | Stale facts "do not degrade gracefully" | Savkin | code has a correct answer; an approximation is actively misleading | agent goes down the wrong path with full confidence |
| E10 | Team conventions resist central authorship | Savkin | institutional memory is a negotiated fiction | documents nobody trusts or follows |
| E11 | File-based memory "works with one, but when you scale past one it creates a problem" | Malcolm | memory scoped to a user/harness doesn't compose across people | lock-in; no team-level compounding |
| E12 | Failed executions are reusable experience | Alake | store the failure, retrieve it on the next attempt | teams repeat dead ends |
| E13 | Tool sprawl confuses agents | OpenAI | overlapping tools create ambiguity | unreliable tool selection |

---

## 3. Causal model

Three structural causes, plus one human one:

1. **Boundary tax.** Context is lost at every boundary crossed: repo, service, team, timezone, branch, session, agent. Cost is roughly linear in boundaries (E4, E5). Every additional repo or shift multiplies explanations.
2. **Wrong layer recorded.** Our tooling records the lower graph — code, commits, CI (E3). The upper graph — sessions, intent, decisions, rejected options, discovered constraints — is stored only in human heads and ephemeral context windows (E2, E5).
3. **Non-graceful drift.** Code memory that is stale is worse than absent, because it is trusted (E8, E9). This is why a "bag of distilled facts" design is actively dangerous for code.
4. **Conventions are negotiated, not authored (E10).** Any feature that claims to be the team's authority on "how we do things" will be distrusted. Precedent (examples of work that succeeded) is acceptable; policy is not.

**Therefore the product's job is:** preserve the upper graph across boundaries, keep it materializable against ground truth, and never present a stale artifact as current.

---

## 4. The unit of value: a landed handoff

Not a memory item. Not a token. The unit is: **the next actor — human or agent — reaches productive continuation without asking the originator.**

That requires five primitives:

| Primitive | Definition | Source |
|---|---|---|
| **Episode** (work session) | A unit of work: intent, repos@SHA, branch, decisions taken, options rejected, dead ends, agent traces, PR/CI links, participants | Savkin "transporter"; Savkin three graphs |
| **Derivation** | A semantic note distilled from one or more episodes, always linked back to its source episodes and to code anchors. Guilty until verified. | Savkin (lossy, drift-prone); OpenAI (correctness memory) |
| **Materialization manifest** | Everything needed to reconstruct the working state: repos + SHAs, branch/worktree, setup commands, priming prompt. Git does the checkout; we supply the reasoning. | Savkin — "recall is not enough" |
| **Structural index** (lower graph) | Repos, packages, API producers/consumers, entry points, build/test commands. Commit-pinned, always current. | OpenAI layers 1/3; Savkin repo graph |
| **Graphs** | Session graph (units of work), repository graph, code-change graph. Repo proximity strengthens session edges; time and participant overlap shape both. | Savkin "three graphs instead of one bag of facts" |

---

## 5. Capability ranking

Impact × effort, derived from the evidence. **Ship order is the last column.**

| Capability | Metric it moves | Evidence | Impact | Effort | Order |
|---|---|---|---|---|---|
| **C1 Episode capture** — hooks capture session → episode record attached to branch/commit/repos@SHA, agent-agnostic | handoff, re-explanation | E2, E4, E5 | high | med | **1** |
| **C2 Materialize / resume** — `ctx materialize <episode>`: checkout repos@SHA, emit priming prompt; hand to another person *or agent* | handoff, review | E2, E4; Savkin transporter | very high | med-low (git does the work) | **2** |
| **C3 Structural index** — lower graph: layout, deps, API producer/consumer edges, commands | orientation, cross-repo scope | E1, E5; OpenAI layers 1/3 | high | med | **3** |
| **C4 Why-is-this-here** — commit/line → episode lookup (git blame → session) | archaeology, review | E3, E4 | med-high | low-med | 4 |
| **C5 Correctness-critical derivations** — constraints/gotchas, code-anchored, verified before serving | rework | E7, E8, E9 | med (harmful if unverified) | med | 5 |
| **C6 Live overlap detection** — PR/branch connector: who is touching which paths; cross-repo CI as one vector | duplicate work, integration | E6 | med | **low** | 5 |
| **C7 Expert routing** — "who has done this kind of change / who should review" | routing | Savkin | med | low (free once C1 exists) | 6 |
| **C8 Episode-graph retrieval** — session/repo/change graphs + hybrid search, locality without tunnel vision | precedent, archaeology | Savkin three graphs | high | high | 6 (start simple, grow) |
| **C9 Derived semantic digests** — PRD-style summaries, dedup/merge | marginal | E9, E10 | low for code | high | **last, deliberately** |

**Note on ordering:** this reverses v0.1, which was semantic-note-centric. Savkin built episodic-first *on purpose*, and his reasoning (lossiness, drift, materialization) applies directly to coding work. Semantic distillation is not removed — it is deferred and made subordinate to episodes.

---

## 6. Design implications (deltas from v0.1)

1. **Episode is the primary aggregate**, not `MemoryItem`. Memory items become *derivations* that point at episodes and code anchors.
2. **Materialization is a headline capability**, not an export feature. "Recall is not enough" (Savkin). Git provides the territory; we provide the map *and* the route back to it.
3. **Three graphs** drive retrieval (session, repository, code-change) — not one embedding index.
4. **Staleness handling becomes verification-first:** derivations are guilty until code-anchors confirm; episodes are history and are re-materialized before acting on them. Serving a stale derivation silently is a bug, not a degradation.
5. **Precedent, not policy.** We surface episodes that did a thing well. We never author "the team standard" (E10).
6. **Both memory axes are in scope:** space (repo graph, C3) *and* time (session graph, C1/C2). Attacking only one leaves the bottleneck (E4, E5).
7. **ACL inheritance stays:** resuming an episode requires access to every repo in it; transcript availability is explicit, not implied (Savkin's operational boundaries; OpenAI pass-through permissions).
8. **Retrieval is push + pull:** a budgeted pack at `SessionStart`, tools for on-demand pull later (Alake's agentic RAG).
9. **Small tool surface** (E13). One read, one search, one write, one materialize.

---

## 7. Hypotheses to falsify in Phase 0

We are not certain the design is right. These are the bets, with tests. **All tests run on first-party data** — events emitted by the recorder running in observe-only mode on pilot teams. No external session logs, no surveys, no analytics retrofits.

| # | Hypothesis | Test | If falsified |
|---|---|---|---|
| H1 | Handoffs and reviews dominate team-speed loss | Observe-mode data across 2 pilot teams: split session time into orientation / action / rework / waiting; measure re-derivation rate and overlap | If orientation/onboarding dominates, re-rank C3 first and demote C1/C2 |
| H2 | Episode + materialization beats fact retrieval | A/B inside the product: (a) episode + materialize, (b) distilled facts, (c) baseline. Measure time-to-substantive-review and correctness | Invest in the semantic layer instead; C9 moves up |
| H3 | Stale context is worse than missing context | Inject stale derivations; measure agent misdirection and human detection rate | If humans reliably catch it, stale flags suffice; drop mandatory verification |
| H4 | Automatic capture is acceptable | Measure install rate, capture rate, policy objections during observe mode | Fall back to manual/pull-only capture, accepting lower coverage |
| H5 | Precedent beats policy for consistency | Compare bespoke vs. precedent-following implementations for review churn | If policy wins, add a curated standards feature (against E10) |
| H6 | Time savings and token savings correlate | Correlate per-session token spend with handoff/rework metrics in observe mode | Report time only; stop reporting token savings |

**H1 is the gate.** If handoffs and reviews are not where the hours go, the entire product thesis needs re-derivation before any code is written.

---

## 8. Discovery questions for pilot teams

Phase 0 must answer these from the actual teams, not from literature:

1. Where are the handoffs, concretely — timezones, repos, PR review, on-call, contractor boundaries?
2. Which of the seven primary metrics hurts most, and what is its current baseline number?
3. What is the harness mix, and what is the actual policy on hook installation and transcript capture?
4. What data may leave a laptop — code bodies, paths, traces, or nothing?
5. Which repos/subsystems are the worst offenders (most explanations per change)?
6. Who reviews what, and how often is review blocked on author availability?

---

## 9. What we deliberately do not build

- Prompt assembly, compaction policy, or anything the harness owns (Wooders; PLAN §4.0).
- An authority on team conventions or standards (E10).
- A general wiki/notes app; we serve work, not documentation.
- Automatic resolution of contradictory memories — surface disputes, let humans decide.
- A meta-harness that orchestrates multi-repo edits and CI. Polygraph does that; we supply the portable, open memory layer that any harness can use. (Revisit only if H1/H2 point there.)
