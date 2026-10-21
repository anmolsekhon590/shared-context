# Inspiration & Reading List

Sources that shaped this project, with notes on what each one contributes to the design. Ordered by load-bearing-ness, not by date.

| # | Source | Type | What we take from it |
|---|---|---|---|
| 0 | [Savkin — *Agentic Memory: Why Code Is Fundamentally Different*](savkin-agentic-memory.md) | Essay (Nx, ~Jul 2026) | **The design spine**: episodic-first, materialization > recall, three graphs, non-graceful drift |
| 1 | [Savkin — *A Genius With Amnesia*](genius-with-amnesia-savkin.md) | Talk (AI Engineer) | "One change, seven explanations," space/time constraints, the transferable unit |
| 2 | [Kay Malcolm — *No Memory, No Harness*](no-memory-no-harness-kay-malcolm.md) | Talk + full transcript (AI Engineer) | The problem statement, the memory broker, five memory types, single-store argument |
| 3 | [*Inside OpenAI's in-house data agent*](2026-01-openai-in-house-data-agent.md) | Engineering blog (Jan 2026) | Six-layer context model, correctness-critical capture, pass-through permissions, evals-as-unit-tests |
| 4 | [*Harness memory ownership*](2026-04-harness-memory-ownership.md) — Harrison Chase + Sarah Wooders | Blog posts (Apr 2026) | Why memory must be open/owned; **and the strongest counter-argument to our architecture** (PLAN §4.0) |
| 5 | [Alake — *Architecting Agent Memory*](architecting-agent-memory-alake.md) | Talk (AI Engineer) | Provider vs. management split, workflow/failed-execution memory, agentic RAG |
| 6 | [Sarah Wooders — *Why Memory Isn't a Plugin*](https://www.letta.com/blog/why-memory-isnt-a-plugin/) | Blog (Apr 2026) | Harness-controlled context decisions: compaction, AGENTS.md loading, system-instruction editing |
| 7 | [Letta — *Context Constitution*](https://www.letta.com/blog/context-constitution/) | Blog (Apr 2026) | Learning as active context management; multi-conversation memory; background memory organization |

**Synthesis:** the evidence is distilled into a problem model at [`../design/00-team-speed-model.md`](../design/00-team-speed-model.md) — that document, not this list, is the design input.

## Related AI Engineer talks

- **12-Factor Agents** (`8kMaTybvDUw`) — owning control flow, context, and tools; deterministic software around the model. Not yet extracted; link only.
- Two previously-listed talks are now extracted: *A Genius With Amnesia* (#1) and *Architecting Agent Memory* (#5).

## The third citation is unidentified

Malcolm says she read "three papers" but the transcript names only two. The AI Engineer talk page's editorial article also references only the OpenAI data agent and Harrison Chase. Possible third: the Anthropic context-engineering guidance, the Letta material above, or a slide-only reference not recoverable from the recording. Flagged rather than guessed.

## Note on the transcript file

`no-memory-no-harness-kay-malcolm.md` includes the transcript **verbatim** for internal research, with source checksum and canonical link. If this repo ever goes public, replace the body with a link + our notes to respect the publisher's rights.
