# Harness memory ownership — distilled notes

**Sources:**
- Harrison Chase (LangChain), *Your harness, your memory*, Apr 11 2026. <https://www.langchain.com/blog/your-harness-your-memory>
- Sarah Wooders (Letta), *Why Memory Isn't a Plugin*, Apr 3 2026. <https://www.letta.com/blog/why-memory-isnt-a-plugin/>
- Letta, *Context Constitution*, Apr 2 2026. <https://www.letta.com/blog/context-constitution/>

This is the **strongest counter-argument to our architecture**, so read it as a design constraint, not as validation.

## The ownership argument (Chase)

Agent harnesses (Claude Code, Codex, Deep Agents, OpenCode, Letta Code, pi) are the dominant way to build agents and they are not going away — Claude Code's leaked source was 512k lines; that code *is* the harness.

> "If you used a closed harness — especially if it's behind a proprietary API — you are choosing to yield control of your agent's memory to a third party."

Escalating badness:
- **Mildly bad:** stateful APIs (OpenAI Responses, Anthropic server-side compaction) store state server-side; you can't switch models and resume threads.
- **Bad:** closed harnesses (Claude Agent SDK) interact with memory in unknown shapes → artifacts are **non-transferrable between harnesses**.
- **Worst:** whole harness including long-term memory behind an API — zero ownership or visibility.

Concrete example: **Codex is open source, but emits an encrypted compaction summary that is not usable outside OpenAI's ecosystem.** Memory is the lock-in mechanism model providers have that the model alone doesn't.

> "Without memory, your agents are easily replicable by anyone who has access to the same tools. With memory, you build up a proprietary dataset."

Their answer: open source, model-agnostic, open standards (`agents.md`, skills), BYO Postgres/Mongo/Redis, self-hostable. Note the convergence: **this is the same posture we're taking, one layer up.** They solve it for an individual agent's memory; nobody is solving it for a team's shared memory.

## The counter-argument (Wooders)

> "Asking to plug memory into an agent harness is like asking to plug driving into a car. Managing context, and therefore memory, is a core capability and responsibility of the agent harness."

- Memory is not a standalone service. RAG *can* be a plugin, but retrieval is only a slice of memory — it doesn't control what the agent actually sees turn-by-turn.
- The harness silently decides: how `AGENTS.md`/`CLAUDE.md` get loaded, how skill metadata is presented, whether the agent can edit its own system instructions, **what survives compaction**, whether interactions are stored and queryable, how memory metadata is presented, how the CWD/filesystem is represented.
- MemGPT was misread as RAG; it was really a *stateful harness* where memory emerges from (a) tools to rewrite prompts/manage external state and (b) the harness's context management.

## Why this matters for us — and our answer

If we claim "we are your agent's memory," this critique lands and we lose. Our positioning must be precise:

> **The harness owns working memory. We own durable *shared* memory.** The context window, compaction policy, and prompt assembly belong to the harness. We are the team-level broker for what persists across sessions, people, branches, and forks — and we make it portable.

Two design consequences:

1. **We are not a passive tool that sits there.** Being a plain MCP server would leave all the important moments in the harness's hands. We must hook the lifecycle: `SessionStart` (inject a pack), **`PreCompact` (snapshot the context that is about to die — this is the single most valuable hook in the entire product)**, `Stop`/`SessionEnd` (distill). MCP is the API; hooks are the heartbeat.
2. **Portability is a feature, not an export format.** Every durable artifact we store must be human-readable, harness-neutral, and leave-taking-able: `.context/` markdown, `AGENTS.md`-compatible summaries, plain JSON. Never an encrypted blob. If a team leaves our server, they keep their memory in a form any harness can consume. This is the exact property Chase says is missing from Codex's compaction summaries and Anthropic's managed agents.

**The corollary our own §4.0 has to state:** we should not attempt to control prompt assembly, compaction, or what the harness does with our pack. We provide a budgeted, provenance-tagged, freshness-scored pack and let the harness decide. Fights over control of the context window are unwinnable and unnecessary — sharing is the actual gap.

## Also worth stealing

- Their contrast between **model-agnostic + open standards + BYO database + self-host** is the distribution posture the community rewards. We should match it exactly: `agents.md` and skills compatibility, Postgres BYO, Docker, no proprietary format, no telemetry by default.
- "Right now, memory as a concept is in its infancy... there are not well known or common abstractions for memory." True, and it means the data model (§4.1) is where the durable contribution is. The MCP surface can change; the schema and the export format are the contract worth getting right.
