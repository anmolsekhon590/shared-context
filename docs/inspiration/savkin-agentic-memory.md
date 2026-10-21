# Agentic Memory: Why Code Is Fundamentally Different — distilled notes

**Source:** Victor Savkin (Nx), *Agentic Memory: Why Code Is Fundamentally Different*, Nx blog (~Jul 2026).
<https://nx.dev/blog/agentic-memory-why-code-is-fundamentally-different>

The single best design document for this project. It is the written form of the *A Genius With Amnesia* talk, and it inverts the usual "distill everything into facts" approach.

## Two dimensions (the classification grid)

**Dimension 1 — memory types:**
- **Working memory** — the context window plus affordances stacked on top; short-lived, session-scoped. Orchestration lives here.
- **Episodic memory** — the recording. "The security-camera footage of a task." What was considered, what was rejected, how it went from empty file to merged PR. Tied to a unit of work. *It does not summarize. It shows.*
- **Semantic memory** — the distilled version: facts, PRDs, design docs. "The decisions made, not the meeting minutes." Shorter, more portable, **lossy**.

"Most tools that say 'memory' often mean semantic. It is the easiest to demo because a list of facts looks like knowledge."

**Dimension 2 — purpose:**
- **Personalized** (about you) — easy to capture: only one person to agree with.
- **Institutional** (scaled to a team) — "far harder to build, not for technical reasons but for human ones... Team preferences require agreement, and teams rarely agree cleanly on how things 'should' be done. **The document that claims to speak for the team is usually a negotiated fiction.**"
- **Code memory** — focuses on how the code itself was produced. "Not 'Victor likes tabs' but 'this retry logic exists because the payment API times out under load, and **here is the session where that was discovered and handled**.'"

## "Docs rot. Code does not."

The trust ordering, most to least reliable:
1. **The code itself** — "the only artifact in the stack that is, by definition, current. Code never lies about what it does, because it is the thing that does it."
2. **Episodic memory** — less abstract, less likely wrong, but still "a recording of a past state, and the world has moved since."
3. **Semantic memory** — most abstract, most likely wrong. "Compression discards the details that turn out to matter."

The central claim: **"the most important capability is not better recall. It is materialization: the ability to pull down the actual state of any session, spin it up, and look at the ground truth."**

Why materialization wins:
- A fact set "can only answer the questions someone thought to record. A running system answers the questions you actually have."
- Enables speculative experiments (change a property, see what breaks).
- **Doing by example beats consuming facts** — for consistency and predictable questions, "show the agent the real code that solved a problem and let it replicate the shape."

## Why code is structurally different

- **Coding produces hard artifacts.** A Slack thread does not. In code "there usually is [a single correct answer], and it lives in the code."
- **Most coding is formulaic.** When work follows established patterns, replicating an existing solution is what produces consistency.
- **Drift is real in code in a way it is not elsewhere.** This is the sharpest sentence in the paper:

> "A stale fact about your codebase does not degrade gracefully. It sends the agent down the wrong path with full confidence."

A doc about org ownership is understood as an approximation. A doc about code is read as fact. So wrong context is worse than missing context.

## Three graphs instead of one bag of facts

Most retrieval is RAG-over-embeddings or an extracted-fact knowledge graph — both "built to serve semantic memory, a pile of statements you query." Episodic memory has a different shape:

1. **Session graph** — each node is a unit of work.
2. **Repository graph** — nodes are repos.
3. **Code change graph** — similarity/relationships of actual diffs.

The repo graph shapes the session graph: sessions touching the same repos get stronger edges. Other forces: similarity of descriptions, logs, commit messages; the developers who participated; similarity of the actual code changes; and **time** (last week ≈ more relevant than three years ago). As sessions accumulate, clusters of repos that co-occur draw new edges.

Payoff: "retrieval that understands locality without being trapped by it. Most of the episodes you need will be close by... But some of the ones that matter most will be surprising and far away."

## Workflows this unlocks (all team-speed mechanisms)

- Review a coworker's PR by materializing the session behind it — "instead of reverse-engineering intent from a diff."
- Establish best practices by finding sessions that did a thing well; build new code example-first.
- Why is this code like this? Start from a commit or single line, jump to the session, recover the decision.
- Resume someone else's in-progress work on your own machine.
- Point an agent at a specific past session to fix a bug or continue a half-finished feature.
- Answer *people* questions: who is the domain expert for this kind of change, and who should review it.

"A pile of facts cannot tell you what was rejected and why. It cannot be spun up and interrogated."

## Where Polygraph sits (their choice, and why it matters to us)

Today: working memory (orchestration) + **episodic-by-code**. Semantic-by-code is on the roadmap, **but episodic comes first on purpose**. That ordering is the direct evidence for our own phase ordering.

## Consequences for our design

1. **Episodic-first.** Capture the session (intent, decisions, dead ends, traces, repos@SHA), don't lead with distilled notes.
2. **Materialization is the headline capability**, not search. Recall without the ability to check the territory is a map you can't trust.
3. **Semantic notes are guilty until verified.** Every derived note must carry code anchors and be re-checked before being presented as current.
4. **Precedent, not policy.** Never author "the team standard." Surface the sessions that did it well and let humans negotiate — institutional memory is a negotiated fiction, and pretending otherwise destroys adoption.
5. **Three graphs, not one bag of facts** for the data model and retrieval.
