# 02 — Data Model

**Status:** draft for review. Postgres 16 + `pgvector` + `ltree`. This is the durable contribution (§4.1 of PLAN): the MCP surface can change, the schema and export format cannot.

**Scope:** the storage model for episodes, derivations, the structural index, the three graphs, ACLs, and **first-party measurement events**. Out of scope: retrieval ranking (04), capture pipeline mechanics (03), wire protocol (01).

---

## 1. Terminology (fix these words now)

| Term | Meaning | Cardinality |
|---|---|---|
| **Episode** | A unit of work. The transferable unit. Intent, repos@SHA, decisions, dead ends, links. | 1 episode : N agent sessions |
| **AgentSession** | One harness execution (a Claude Code / Codex / pi session). | N : 1 |
| **Materialization** | An attempt to reconstruct an episode's state on a machine and continue it. | N : 1 |
| **Derivation** | A distilled note linked to source episodes and code anchors. Guilty until verified. | N : N |
| **Event** | An immutable observation emitted by the recorder, a connector, or the server. Powers all metrics. | append-only |

"Session" alone is banned from the schema: it always means AgentSession, never Episode.

## 2. Design principles encoded here

| # | Principle | Where it lives |
|---|---|---|
| P1 | Episodic-first; derivations subordinate to episodes | `derivations` requires ≥1 `derivation_source` |
| P2 | Recall is not enough — materialization is the capability | `materializations` + `episode_repos` @ SHA + `manifest` |
| P3 | Stale context is a bug, not a degradation | `derivation_anchors.state`, `derivations.status`, verification fields |
| P4 | Shared memory is untrusted input | `provenance`, `events.source`, visibility rules; no instruction fields |
| P5 | ACLs inherit from sources (pass-through) | `repo_access`, `derivation_sources`, resolution rules §5 |
| P6 | Precedent, not policy | no `team_standard` table; `derivation_kind='precedent'` points at episodes |
| P7 | Measurement is a byproduct of capture | `events` + `agent_sessions` signals, observe-only mode |
| P8 | Portability | every table is exportable to `.context/` markdown + JSON; no proprietary blobs |
| P9 | Three graphs, not one bag of facts | `graph_edges` with session/repo/change edge types |
| P10 | Small tool surface | schema exposes few, wide read models (`context_pack`), not many narrow ones |

## 3. Entity map

```
principals ──< namespace_members >── namespaces (ltree)
     │                                   │
     │ repo_access                       │
     ▼                                   │
   repos ──< episode_repos >── episodes ─┴──< episode_decisions
     │                           │  │            episode_dead_ends
     │                           │  └──< episode_links (pr|ci|issue|commit)
     │                           │  └──< materializations
     │                           │
     │        agent_sessions >───┘        derivations ──< derivation_sources
     │             │                          │
     │             └──< session_signals       └──< derivation_anchors
     │
     └──< packages / index_entries / graph_edges

events  (append-only, partitioned by month)  →  metrics_daily (rollup)
audit_log · tombstones
```

## 4. Core tables

### 4.1 Namespaces, principals, ACL

```sql
CREATE TABLE namespaces (
  id          uuid PRIMARY KEY,
  parent_id   uuid REFERENCES namespaces(id),
  kind        text NOT NULL CHECK (kind IN ('org','team','project','repo','user')),
  slug        text NOT NULL,
  path        ltree NOT NULL,              -- org.eng.platform.api
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (parent_id, slug)
);
CREATE INDEX ON namespaces USING gist (path);

CREATE TABLE principals (
  id           uuid PRIMARY KEY,
  kind         text NOT NULL CHECK (kind IN ('user','agent','service')),
  external_id  text,                        -- OIDC sub / GitHub login
  display_name text NOT NULL,
  agent_model  text,                        -- when kind='agent'
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kind, external_id)
);

CREATE TABLE namespace_members (
  namespace_id uuid NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
  principal_id uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
  role         text NOT NULL CHECK (role IN ('reader','writer','reviewer','admin')),
  PRIMARY KEY (namespace_id, principal_id)
);

-- synced from the forge; the source of truth for the pass-through rule
CREATE TABLE repo_access (
  principal_id uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
  repo_id      uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  can_read     boolean NOT NULL DEFAULT false,
  can_write    boolean NOT NULL DEFAULT false,
  synced_at    timestamptz NOT NULL,
  PRIMARY KEY (principal_id, repo_id)
);
```

### 4.2 Repos and the structural index (lower graph)

```sql
CREATE TABLE repos (
  id             uuid PRIMARY KEY,
  namespace_id   uuid NOT NULL REFERENCES namespaces(id),
  forge          text NOT NULL CHECK (forge IN ('github','gitlab','local')),
  full_name      text NOT NULL,             -- org/name
  default_branch text NOT NULL DEFAULT 'main',
  head_sha       text,
  indexed_sha    text,
  indexed_at     timestamptz,
  UNIQUE (forge, full_name)
);

CREATE TABLE index_entries (            -- commit-pinned, no LLM
  id         uuid PRIMARY KEY,
  repo_id    uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  commit_sha text NOT NULL,
  kind       text NOT NULL CHECK (kind IN ('entry_point','command','module','service','manifest')),
  name       text NOT NULL,
  path       text,
  meta       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON index_entries (repo_id, commit_sha);

CREATE TABLE packages (
  id       uuid PRIMARY KEY,
  repo_id  uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  name     text NOT NULL,
  version  text,
  manifest_path text,
  UNIQUE (repo_id, name)
);

CREATE TABLE api_surfaces (             -- producer/consumer edges for cross-repo reach
  id            uuid PRIMARY KEY,
  repo_id       uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  package_id    uuid REFERENCES packages(id) ON DELETE CASCADE,
  role          text NOT NULL CHECK (role IN ('producer','consumer')),
  symbol        text NOT NULL,
  path          text,
  contract_hash text,
  meta          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON api_surfaces (role, symbol);
```

### 4.3 Episodes

```sql
CREATE TYPE episode_status AS ENUM ('open','handed_off','in_review','closed','abandoned');

CREATE TABLE episodes (
  id            uuid PRIMARY KEY,               -- UUIDv7, client-generated (time-sortable)
  namespace_id  uuid NOT NULL REFERENCES namespaces(id),
  title         text NOT NULL,
  intent        text NOT NULL,                  -- what are we trying to do
  status        episode_status NOT NULL DEFAULT 'open',
  summary       text,                           -- short generated digest, for lists only
  created_by    uuid NOT NULL REFERENCES principals(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  closed_at     timestamptz,
  handed_off_to uuid REFERENCES principals(id),
  decision_count int NOT NULL DEFAULT 0,        -- denormalized list-view fields
  dead_end_count int NOT NULL DEFAULT 0,
  acl_mode      text NOT NULL DEFAULT 'strict' CHECK (acl_mode IN ('strict','namespace')),
  embedding     vector(1024),
  fts           tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || intent || ' ' || coalesce(summary,''))) STORED
);
CREATE INDEX ON episodes USING gin (fts);
CREATE INDEX ON episodes USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON episodes (namespace_id, status, updated_at DESC);
```

```sql
CREATE TABLE episode_repos (
  episode_id uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  repo_id    uuid NOT NULL REFERENCES repos(id),
  role       text NOT NULL DEFAULT 'touched' CHECK (role IN ('primary','touched','dependency')),
  base_sha   text,
  head_sha   text,
  branch     text,
  fork       text,
  PRIMARY KEY (episode_id, repo_id)
);

CREATE TABLE episode_decisions (
  episode_id  uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  seq         int  NOT NULL,
  what        text NOT NULL,
  why         text NOT NULL,
  options_rejected jsonb NOT NULL DEFAULT '[]',
  evidence_refs    jsonb NOT NULL DEFAULT '[]',  -- message ids, file paths, links
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (episode_id, seq)
);

CREATE TABLE episode_dead_ends (
  episode_id uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  seq        int NOT NULL,
  tried      text NOT NULL,
  outcome    text NOT NULL,
  evidence_refs jsonb NOT NULL DEFAULT '[]',
  PRIMARY KEY (episode_id, seq)
);

CREATE TABLE episode_links (
  id          uuid PRIMARY KEY,
  episode_id  uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  kind        text NOT NULL CHECK (kind IN ('pr','ci_run','issue','commit','doc','url')),
  repo_id     uuid REFERENCES repos(id),
  external_id text,
  url         text,
  state       jsonb NOT NULL DEFAULT '{}',      -- pr_state, ci_conclusion, ...
  synced_at   timestamptz,
  UNIQUE (episode_id, kind, external_id)
);
CREATE INDEX ON episode_links (kind, external_id);

-- the transferable unit: how to reconstruct this work somewhere else
CREATE TABLE materializations (
  id            uuid PRIMARY KEY,
  episode_id    uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  requested_by  uuid NOT NULL REFERENCES principals(id),
  harness       text NOT NULL,
  agent_model   text,
  manifest      jsonb NOT NULL,                 -- worktree_spec, setup_commands[], priming_prompt
  status        text NOT NULL DEFAULT 'started' CHECK (status IN ('started','ready','failed','continued')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  ready_at      timestamptz,
  first_edit_at timestamptz,                    -- ← handoff latency numerator
  continued_episode_id uuid REFERENCES episodes(id)
);
CREATE INDEX ON materializations (episode_id);
```

### 4.4 Agent sessions and observe-mode signals (P7)

```sql
CREATE TABLE agent_sessions (
  id            uuid PRIMARY KEY,               -- client-generated UUIDv7
  principal_id  uuid NOT NULL REFERENCES principals(id),
  episode_id    uuid REFERENCES episodes(id) ON DELETE SET NULL,
  harness       text NOT NULL,                  -- claude-code | codex | pi | ...
  agent_model   text,
  repo_id       uuid REFERENCES repos(id),
  git_branch    text,
  cwd_hash      bytea,                          -- HMAC, never the raw path
  started_at    timestamptz NOT NULL,
  ended_at      timestamptz,
  first_edit_at timestamptz,                    -- ✱ orientation time = first_edit_at - started_at
  tool_counts   jsonb NOT NULL DEFAULT '{}',    -- {read, edit, bash, search, web}
  files_read    int NOT NULL DEFAULT 0,
  files_edited  int NOT NULL DEFAULT 0,
  context_overhead_ratio real,                  -- context-gathering calls / total calls
  compaction_count int NOT NULL DEFAULT 0,
  tokens_in     bigint,
  tokens_out    bigint,
  mode          text NOT NULL DEFAULT 'observe' CHECK (mode IN ('observe','active')),
  transcript_ref text,                          -- object-store ref, ACL'd, TTL'd
  restatement_count int NOT NULL DEFAULT 0,     -- locally detected, count only; no text leaves the client
  restatement_classes jsonb NOT NULL DEFAULT '{}',  -- {"as_i_said":1,"context_dump_first_prompt":2}
  restatement_confidence real
);
CREATE INDEX ON agent_sessions (principal_id, started_at DESC);
CREATE INDEX ON agent_sessions (repo_id, started_at DESC);

-- optional hashed-path mode: enables cross-session/cross-user re-derivation
-- measurement without the server ever seeing a file path
CREATE TABLE session_path_signals (
  session_id uuid NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  path_hash  bytea NOT NULL,                    -- HMAC(server_key, repo_id || path)
  repo_id    uuid NOT NULL REFERENCES repos(id),
  reads      int NOT NULL DEFAULT 0,
  searches   int NOT NULL DEFAULT 0,
  edits      int NOT NULL DEFAULT 0,
  PRIMARY KEY (session_id, path_hash)
);
CREATE INDEX ON session_path_signals (repo_id, path_hash);
```

### 4.5 Derivations (guilty until verified)

```sql
CREATE TYPE derivation_kind  AS ENUM ('constraint','gotcha','precedent','decision','fact');
CREATE TYPE derivation_trust AS ENUM ('unverified','verified','disputed','superseded');
CREATE TYPE validity_status  AS ENUM ('active','stale','disputed','superseded','archived');

CREATE TABLE derivations (
  id            uuid PRIMARY KEY,
  namespace_id  uuid NOT NULL REFERENCES namespaces(id),
  kind          derivation_kind  NOT NULL,
  title         text NOT NULL,
  body_md       text NOT NULL,
  est_tokens    int NOT NULL,
  trust         derivation_trust NOT NULL DEFAULT 'unverified',
  status        validity_status  NOT NULL DEFAULT 'active',
  confidence    real,
  created_by    uuid NOT NULL REFERENCES principals(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  ttl_days      int,
  last_verified_at     timestamptz,
  verify_method        text CHECK (verify_method IN ('code_check','test','human')),
  verified_against_sha text,
  supersedes_id    uuid REFERENCES derivations(id),
  superseded_by    uuid REFERENCES derivations(id),
  embedding        vector(1024),
  fts              tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || body_md)) STORED
);
CREATE INDEX ON derivations USING gin (fts);
CREATE INDEX ON derivations USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON derivations (namespace_id, status, kind);

CREATE TABLE derivation_sources (     -- P1: no orphan derivations
  derivation_id uuid NOT NULL REFERENCES derivations(id) ON DELETE CASCADE,
  episode_id    uuid NOT NULL REFERENCES episodes(id) ON DELETE RESTRICT,
  PRIMARY KEY (derivation_id, episode_id)
);

CREATE TABLE derivation_anchors (     -- P3: cheap, local verification
  id            uuid PRIMARY KEY,
  derivation_id uuid NOT NULL REFERENCES derivations(id) ON DELETE CASCADE,
  repo_id       uuid NOT NULL REFERENCES repos(id),
  path          text,
  symbol        text,
  content_hash  text NOT NULL,          -- git blob hash of the referenced content
  commit_sha    text,
  state         text NOT NULL DEFAULT 'match' CHECK (state IN ('match','drift','missing')),
  last_checked_at timestamptz,
  UNIQUE (derivation_id, repo_id, path, symbol)
);
CREATE INDEX ON derivation_anchors (repo_id, state);
```

### 4.6 The three graphs (P9)

One edge table, typed. Heterogeneous on purpose: heuristics will change more often than the nodes.

```sql
CREATE TABLE graph_edges (
  id         bigserial PRIMARY KEY,
  namespace_id uuid NOT NULL REFERENCES namespaces(id),
  src_kind   text NOT NULL CHECK (src_kind IN ('episode','repo','package','derivation','change')),
  src_id     uuid NOT NULL,
  dst_kind   text NOT NULL CHECK (dst_kind IN ('episode','repo','package','derivation','change')),
  dst_id     uuid NOT NULL,
  edge_type  text NOT NULL,   -- episode_touches_repo | episode_related_episode
                              -- repo_depends_on_repo | repo_produces_consumes
                              -- episode_changed_similar_to_episode | derivation_covers_path
  weight     real NOT NULL DEFAULT 1.0,
  method     text,            -- shared_repo | description_similarity | participants |
                              -- change_similarity | time_decay | dependency
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (src_kind, src_id, dst_kind, dst_id, edge_type)
);
CREATE INDEX ON graph_edges (src_kind, src_id, edge_type, weight DESC);
CREATE INDEX ON graph_edges (dst_kind, dst_id, edge_type, weight DESC);
```

`episode_touches_repo` edges are generated from `episode_repos`; the rest are computed by a worker. Time decay is expressed as a recomputed `weight`, not a stored timestamp hack — edges are periodically refreshed.

### 4.7 Events — first-party measurement (P7)

Append-only, partitioned by month. This table is the reason we do not need external session logs or surveys.

```sql
CREATE TYPE event_type AS ENUM (
  'episode.created','episode.updated','episode.handed_off','episode.closed',
  'episode.materialized','episode.resume_started','episode.resume_completed',
  'session.started','session.first_edit','session.ended','session.compacted',
  'retrieval.pack_served','retrieval.item_cited','retrieval.no_context_found','retrieval.search',
  'derivation.proposed','derivation.confirmed','derivation.rejected',
  'derivation.verified','derivation.went_stale','derivation.disputed','derivation.forget',
  'rework.linked','overlap.detected','expert.routed',
  'review.started','review.commented','review.approved',
  'resume.feedback'
);

CREATE TABLE events (
  id          bigserial,
  ts          timestamptz NOT NULL,
  namespace_id uuid,
  type        event_type NOT NULL,
  source      text NOT NULL DEFAULT 'client' CHECK (source IN ('client','connector','server','derived')),
  actor_id    uuid,                       -- principal
  session_id  uuid,                       -- agent_session, when applicable
  episode_id  uuid,
  target_episode_id uuid,
  target_principal_id uuid,
  repo_id     uuid,
  duration_ms int,
  tokens_in   bigint,
  tokens_out  bigint,
  payload     jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);
-- monthly partitions; e.g. events_2026_10
CREATE INDEX ON events (namespace_id, type, ts DESC);
CREATE INDEX ON events (episode_id, ts DESC);
```

`source` matters: `client` = emitted by the recorder on a developer machine; `connector` = synthesized from the forge (PR review events); `server` = internal; `derived` = computed by a worker. Metrics never silently mix sources.

### 4.8 Rollups, audit, tombstones

```sql
CREATE TABLE metrics_daily (
  day          date NOT NULL,
  namespace_id uuid NOT NULL,
  metric       text NOT NULL,     -- handoff_latency_p50 | orientation_median | rederivation_rate | ...
  value        jsonb NOT NULL,    -- {p50:..., p90:..., n:...}
  computed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (day, namespace_id, metric)
);

CREATE TABLE audit_log (
  id        bigserial PRIMARY KEY,
  ts        timestamptz NOT NULL DEFAULT now(),
  actor_id  uuid,
  action    text NOT NULL,        -- read | write | verify | forget | promote | export
  object_kind text NOT NULL,
  object_id uuid,
  meta      jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE tombstones (         -- P4: forgotten content must not be re-learned
  content_hash text PRIMARY KEY,
  namespace_id uuid,
  reason       text,
  deleted_at   timestamptz NOT NULL DEFAULT now()
);
```

## 5. ACL resolution (P5)

Retrieval must never leak. Rules, in order:

1. **Episode read** (`acl_mode='strict'`, default): requester holds `can_read` on **every** repo in `episode_repos`. Otherwise deny, and return `redacted` with repo names the requester cannot see. Rationale: Savkin's operational boundary — resuming an episode requires access to every repo in it; OpenAI's agent is strictly pass-through.
2. **Episode read** (`acl_mode='namespace'`): requester is a member of the namespace. Allowed only for episodes with no restricted repo references.
3. **Derivation read**: requester passes rule 1 or 2 for **every** episode in `derivation_sources`. Derivations with zero sources cannot exist (FK `RESTRICT` + builder check).
4. **Unknown provenance** (repo access not yet synced): treat as restricted; never promote above namespace.
5. **Promotion** (private → team → org): explicit event `derivation.confirmed` by a `reviewer`+; an item cannot be promoted above the ACL intersection of its sources.

Read models (`context_pack`) are built **after** filtering, never filtered after building.

## 6. Key queries the model must support

| Query | Path |
|---|---|
| Session-start pack | `repo_id` → local episodes via `graph_edges(episode_related_episode, weight)` + `derivations` FK-joined to `episode_repos` → ACL filter → token budget |
| Resume | `episodes` + `episode_repos` + `episode_decisions` + `episode_dead_ends` + latest `materializations.manifest` |
| Why is this here? | `commit_sha` → `episode_repos` SHA range or `episode_links(kind='commit')` → episode + decisions |
| Staleness sweep | `derivation_anchors.state='match'` → re-hash → `drift` ⇒ `derivations.status='stale'` + `derivation.went_stale` event |
| Overlap | open episodes sharing `repo_id` + overlapping `session_path_signals.path_hash` in a time window ⇒ `overlap.detected` |
| Handoff latency | `events(episode.handed_off).ts` → first `materializations.first_edit_at` |
| Orientation time | `agent_sessions.first_edit_at - started_at`, split by `mode` |
| Re-derivation rate | `session_path_signals` with `reads ≥ 1` in ≥2 sessions (and ≥2 principals) ÷ distinct `path_hash` |
| Expert routing | `graph_edges(episode_related_episode)` → `episodes.created_by` |

## 7. Retention and deletion

| Data | Default | Notes |
|---|---|---|
| `events` | 13 monthly partitions hot, then rolled into `metrics_daily` and dropped | payloads never contain file contents |
| transcripts (`transcript_ref`) | object store, TTL configurable (default 90d) | episode remains useful without traces; delete is per-episode |
| `agent_sessions` signals | kept | only hashes if `hashed_paths` mode |
| `derivations` | never hard-deleted | `forget` ⇒ archive + `tombstones` row |
| `repos`/`index_entries` | current + previous commit only | history lives in git |
| `audit_log` | 24 months | append-only |

## 8. Export format (P8)

Every durable object serializes to harness-neutral files:

```
.context/
├── episodes/<id>.md          # YAML front-matter (ids, repos@SHA, status) + intent/decisions/dead-ends
├── derivations/<slug>.md     # YAML front-matter (kind, trust, anchors) + body
├── repos/<name>/index.json   # IndexEntry snapshot
└── manifest.json             # schema version, UUIDs, checksums
```

Import must round-trip: a team can leave with everything, and another instance can ingest it.

## 9. Open issues

1. **UUIDs** — UUIDv7 client-side (offline capture) vs DB-generated. Lean client-side; needs a small library.
2. **Hierarchy** — `ltree` (used above) vs materialized `path[]`. ltree wins on ancestry queries; adds one extension.
3. **Path-hash key** — who holds the HMAC key, and should hashes be comparable across namespaces? Current answer: per-server key, scoped by `repo_id`; cross-namespace matching disabled.
4. **ACL intersections at scale** — materializing `episode_acl_principals` may be needed if rule 1 becomes a hot join.
5. **Change similarity** — computing `episode_changed_similar_to_episode` is the most expensive worker job; consider sampling diffs, or deferring to Phase 2.
6. **Event schema versioning** — add `schema_version` to payloads now, before clients multiply.
7. **Multi-tenancy** — namespace column everywhere (chosen) vs DB-per-tenant. Revisit at scale; the export format must work for both.
8. **Model meaning in code actions** — `session_path_signals` gives us re-derivation; **RESOLVED:** re-explanation is detected **locally** in the recorder (conservative, explainable rule list first — no model), and only `restatement_count`, `restatement_classes`, and `restatement_confidence` are sent. Default on, visible in the client, one-line opt-out. Contract frozen in D1 (`UserPromptSubmit` hook). If precision <70% during observe mode, demote to a soft signal but keep the event.
