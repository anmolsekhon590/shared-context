# A Genius With Amnesia — distilled notes

**Source:** Victor Savkin (Nx), *A Genius With Amnesia*, AI Engineer. Talk page with full transcript: <https://ai.engineer/talks/a-genius-with-amnesia>.
Companion essay notes: [`savkin-agentic-memory.md`](savkin-agentic-memory.md). Polygraph is commercial, not open source — the gap we fill.

## The metaphor

A genie gives you John Carmack — but he can see one-thousandth of the codebase and remembers nothing from previous conversations. So you must repeatedly explain conventions, completed work, and why things are arranged as they are. **"Intelligence without system context or continuity leaves the human responsible for both."**

## "One change, seven explanations"

Four repos (UI, Module 1, Module 2, Platform); one button change:
1. Explain + implement in UI, publish the library.
2. Explain in Module 1 — discover the published version is incompatible.
3. Return to UI, explain the original change **and** the newly discovered issue to a fresh agent.
4. Fix, republish, re-explain in Module 1.
5. Re-explain in Module 2.
6. Explain how the pieces fit together in Platform.
7. A week later a production bug appears: start a fresh UI session, explain the original change and the production issue again.

Seven explanations for one intent. "Different developers may perform the handoffs; distributing the work does not eliminate the repeated explanations." In a 20-repo change, twenty explanations.

## The two constraints (space and time)

| Constraint | What the agent lacks | What the human supplies |
|---|---|---|
| **Space** | visibility beyond the current repo | system relationships, downstream context |
| **Time** | memory of previous sessions | intent, decisions, prior discoveries |

This is the cleanest statement of the problem we have. Our product must attack both axes.

## The two-layer graph

The missing history is **episodic memory** — knowledge of the sessions in which work happened. Combine episodes with the code they changed and the org is a two-layer graph:

- **Lower layer:** repositories, artifacts, dependencies → *what exists*.
- **Upper layer:** agent sessions and how they modified them → *how it came to be*.

"Repositories relate to repositories; sessions relate to other sessions and to the code they touched." Individual agents see one session and a sliver of code, so developers carry fragments of the graph in their heads. Scale reference: ~1,000 owned repos + tens of thousands of OSS deps.

## The transferable unit

Polygraph is an **agent-agnostic meta-harness**. Its session machinery captures intent, participating repos, PRs, and agent traces. A session can be **restored on another machine**: repos at the same commit SHAs, agents started and connected, primed with captured traces. The demo records a session with **Claude**, then hands it to a backend owner who resumes it with **Codex**.

> **"The transferable unit is the state attached to the session, not just conversational memory."** — the transporter, not the transcript.

Operational boundaries he documents: restoration needs access to every repo in the session, and transcript availability depends on sharing. (→ our ACL inheritance requirement.)

## The workflows (where team time is actually saved)

- **Review:** when a PR raises questions, resume the author's session and ask your agent about the decisions recorded in the traces, "rather than immediately asking the author to reconstruct them." He describes the restored review environment as requiring zero setup. *This removes the reviewer's dependency on the author's availability — a timezone-proof latency cut.*
- **Precedent:** find an earlier respected engineer's session and follow its approach rather than inventing something bespoke. Consistency by example.
- **Archaeology:** from a production bug, reference the original session; the agent retrieves the commits/logs it needs. "A fix without him supplying further context beyond the session reference and bug notice."
- **Scope from the graph:** library updates ("find repos depending on this version"), research ("find repos relevant to this post"), precedent ("find earlier sessions that did related work"). Retrieval runs **in both directions**: current repo prioritizes sessions; current session suggests repos.

## CI as one vector

A ten-repo session can produce ten PRs. Treating CI results independently misses cross-repo interaction failures. Polygraph treats them as one vector and coordinates *where the correction belongs* (consumer patch vs. producer fix) as one unit of work.

## His own caveat (the staleness problem)

From the companion essay: **"a recorded episode describes a past state, which may no longer hold. Having the record within reach does not guarantee that conclusions drawn from it remain correct."** He built episodic-first anyway, because it is less lossy than semantic memory — but materialization exists precisely to check the territory before acting.

## The closing image

In a 1,000-engineer org, each person contributes sessions to a shared body of work, and an agent drawing on that body can have **more context than any single developer carries personally**. The repository graph provides the structure; the session graph provides the accumulated history.

→ That is the same thesis as ours: *shared memory is the team-level multiplier.* He is building it for a meta-harness orchestrating multi-repo changes; we are building it as an open, harness-agnostic shared layer.
