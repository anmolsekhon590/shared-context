# Shared Context

**Git for the reasoning, not just the code.**

A team-shared, episodic-first context layer for coding agents. It captures what
happens in agent sessions, attaches it to the branch/commit/repos it belongs to,
and lets another person (or their agent, in a different harness) resume that work
without re-explaining anything.

Status: **Phase 0 — observe-only recorder.** It captures sessions and measures
where context time goes (orientation, re-derivation, restatement, overlap). No
retrieval or injection yet.

- Plan and evidence: [`PLAN.md`](PLAN.md), [`docs/design/`](docs/design/),
  [`docs/inspiration/`](docs/inspiration/)
- **Phase 0 runbook + H1 decision gates: [`docs/PHASE0.md`](docs/PHASE0.md)**
- Data model: [`docs/design/02-data-model.md`](docs/design/02-data-model.md)
- Wire contract: [`docs/design/01-boundary-and-protocol.md`](docs/design/01-boundary-and-protocol.md)

## Quickstart

```bash
# 1. database
docker compose -f deploy/docker-compose.yml up -d

# 2. server (auto-migrates)
uv run ctx serve --port 8787

# 3. client config + hooks (observe mode; claude-code | pi | all)
uv run ctx login --server http://127.0.0.1:8787 --token dev-token
uv run ctx init --harness all --mode observe --project /path/to/repo

# 4. after some real sessions
uv run ctx report --days 7
```

## Harness support

| Harness | Integration point | Mode |
|---|---|---|
| Claude Code | five command hooks in `~/.claude/settings.json` | observe |
| pi | extension at `~/.pi/agent/extensions/shared-context.ts`, forwards session lifecycle to `ctx hook` | observe only (injection lands in Phase 1) |

Adapters live in `src/shared_context/harnesses/`. A new harness is a transcript
parser plus a thin installer; both parsers share `analyzer.ToolRecorder`, so
metrics stay comparable across harnesses instead of drifting per implementation.

## What is captured

| Capability | Default | Leaves the machine |
|---|---|---|
| Session start/end times, tool counts, tokens | on | aggregate numbers |
| `first_edit_at` (orientation time) | on | timestamp |
| Path signals (re-derivation) | on | `HMAC(path)` only |
| Restatement detection | on | counts + pattern class |
| Transcript upload | **off** | nothing |

Every capability is independently switchable (`ctx init --help`, `ctx config`).
Hooks fail open: a broken recorder never blocks a session.

## Layout

```
src/shared_context/       # server + cli + analyzer (single package, split later)
  server/                 # FastAPI ingest + report API
  harnesses/              # claude_code + pi adapters (install + transcript parse)
  migrations/             # plain SQL, applied in order
deploy/docker-compose.yml # postgres 16 + pgvector
docs/                     # plan, design, evidence
```
