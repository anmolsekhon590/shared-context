# Phase 0 Runbook — observe mode

**Goal:** answer H1 from first-party data. *Do handoffs, orientation, and re-derivation actually dominate team-speed loss?* The recorder is built; this is how to run it and what the numbers mean.

No external logs, no surveys, no prompt text, no raw paths. Metrics come from events the recorder emits while doing its job.

## 1. Setup (one engineer, 10 minutes)

```bash
docker compose -f deploy/docker-compose.yml up -d
uv run ctx serve --port 8787 &        # leave running; auto-migrates
uv run ctx login --server http://127.0.0.1:8787 --token dev-token   # set CTX_API_TOKEN when shared
uv run ctx init --harness all --mode observe --project /path/to/repo
uv run ctx doctor                      # health, per-harness install state, spool
```

`--harness` accepts `claude-code`, `pi`, or `all`. Both are observe-only in Phase 0;
the pi extension lives at `~/.pi/agent/extensions/shared-context.ts` and is removed
cleanly by `ctx uninstall`.

For a shared server: set `CTX_API_TOKEN` to a real secret, and put it behind your VPN/reverse proxy. Phase 0 has a single flat token; per-user OIDC arrives with active mode.

**Each participating engineer** runs `ctx login` + `ctx init` once, for each repo they work in. Consent is printed at install time:

| Captured | Default | What leaves the machine |
|---|---|---|
| Session timing, tool counts, tokens | on | aggregate numbers |
| `first_edit_at` | on | timestamp |
| Path signals | on | `HMAC(path)` only |
| Restatement | on | count + pattern class |
| Transcript | **off** | nothing |

## 2. Run it (1–2 weeks of normal work)

- 2+ engineers on the **same repo**, working normally. Cross-user numbers require two principals; one person alone can only produce within-user re-derivation. Harnesses may differ (one on Claude Code, one on pi) — the metrics are computed by the same shared recorder in both.
- Long enough to see repetition: ~10+ sessions per person, or one week minimum.
- Offline/blocked? `ctx spool status` / `ctx spool flush`. Hooks never block a session.
- Check in mid-week: `ctx report --days 7`.

## 3. Read the report

```
ctx report --days 7
```

| Metric | What it means | Signal to look for |
|---|---|---|
| **Orientation p50/p90** | session start → first edit. Time before productive work. | p50 > 5 min consistently |
| **Re-derivation (within-user)** | paths read in ≥2 sessions by the same person | high = session-scoped amnesia |
| **Re-derivation (cross-user)** | paths read by ≥2 *different* people | **the handoff metric.** 0 means people aren't stepping on shared context |
| **Restatement** | locally detected "as I said…" / context-dump prompts | > 0.5 per session = re-explaining intent |
| **Overlap** | paths co-touched by 2+ principals in 48h | late-discovered collisions |
| **Context overhead** | explore ÷ (explore + mutate) | > 0.6 = context-heavy, not implementation-heavy |
| **Tokens** | secondary; the cost constraint | cost per merged change, never a goal |

## 4. The H1 gate

**Proceed to active mode if any two of:**

- orientation p50 > 5 min, **and**
- (cross-user re-derivation rate > 0.2 **or** restatement ≥ 0.5/session **or** overlap > ~5 paths/week)

**Re-rank instead if:** orientation dominates but re-derivation is *within-user only* → the problem is session continuity, not team handoff. C3 (structural index / orientation pack) moves first; handoff features wait.

**Stop if:** all of the above are near zero after two weeks. Then the context tax is not where the evidence said it was, and the plan needs re-derivation before more building.

Record the decision in `PLAN.md` with the raw numbers and the date. Numbers beat narrators.

## 5. Privacy verification (run this before telling anyone "it's private")

```bash
psql postgresql://ctx:ctx@127.0.0.1:55432/ctx -c "
  SELECT count(*) AS path_rows, octet_length(min(path_hash)) AS hash_bytes FROM session_path_signals;
  SELECT count(*) FROM events WHERE payload::text ILIKE '%src/%';       -- expect 0
  SELECT column_name FROM information_schema.columns
    WHERE table_name='agent_sessions' AND column_name ILIKE '%path%';   -- only cwd_hash
"
```

What the database actually contains: hashed paths (32-byte HMAC), timestamps, counts, token totals, repo `owner/name`, hashed principal ids. No file contents, no prompts, no absolute paths, no transcripts.

**Right to delete:** `DELETE FROM agent_sessions WHERE principal_id = '<id>'` cascades path signals; events referencing the session remain unless deleted too. Full reset: `docker compose down -v`.

## 6. What happens next (Phase 1 preview)

If the gate passes, active mode adds retrieval and injection — `get_context` at `SessionStart`, episodes materialized via `ctx materialize`, and the H2 test: *episode + materialize* vs. *distilled facts* vs. *baseline* on real review tasks. The observe-mode baselines recorded here become the counterfactual, so the H2 claim is measured, not asserted.
