-- 0001_init.sql — schema for Phase 0 (observe-only) plus forward tables.
-- See docs/design/02-data-model.md. Deviations from the design doc are noted:
--   * events is a plain table (partitioning deferred until volume justifies it);
--     id is a client-generated UUIDv7 primary key for idempotent ingest.
--   * derivations.embedding is nullable and unused until retrieval ships.

CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- namespaces

CREATE TABLE namespaces (
  id          uuid PRIMARY KEY,
  parent_id   uuid REFERENCES namespaces(id),
  kind        text NOT NULL CHECK (kind IN ('org','team','project','repo','user')),
  slug        text NOT NULL,
  path        ltree NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (parent_id, slug)
);
CREATE INDEX namespaces_path_gist ON namespaces USING gist (path);

INSERT INTO namespaces (id, kind, slug, path)
VALUES ('00000000-0000-0000-0000-000000000001', 'org', 'local', 'local')
ON CONFLICT DO NOTHING;

CREATE TABLE principals (
  id           uuid PRIMARY KEY,
  kind         text NOT NULL CHECK (kind IN ('user','agent','service')),
  external_id  text,
  display_name text NOT NULL,
  agent_model  text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kind, external_id)
);

CREATE TABLE namespace_members (
  namespace_id uuid NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
  principal_id uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
  role         text NOT NULL CHECK (role IN ('reader','writer','reviewer','admin')),
  PRIMARY KEY (namespace_id, principal_id)
);

-- ------------------------------------------------------------------- repos

CREATE TABLE repos (
  id             uuid PRIMARY KEY,
  namespace_id   uuid NOT NULL REFERENCES namespaces(id),
  forge          text NOT NULL CHECK (forge IN ('github','gitlab','local')),
  full_name      text NOT NULL,
  default_branch text NOT NULL DEFAULT 'main',
  head_sha       text,
  indexed_sha    text,
  indexed_at     timestamptz,
  UNIQUE (forge, full_name)
);

-- Pass-through ACL source (synced from the forge; empty in Phase 0).
CREATE TABLE repo_access (
  principal_id uuid NOT NULL REFERENCES principals(id) ON DELETE CASCADE,
  repo_id      uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  can_read     boolean NOT NULL DEFAULT false,
  can_write    boolean NOT NULL DEFAULT false,
  synced_at    timestamptz NOT NULL,
  PRIMARY KEY (principal_id, repo_id)
);

CREATE TABLE index_entries (
  id         uuid PRIMARY KEY,
  repo_id    uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  commit_sha text NOT NULL,
  kind       text NOT NULL CHECK (kind IN ('entry_point','command','module','service','manifest')),
  name       text NOT NULL,
  path       text,
  meta       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX index_entries_repo ON index_entries (repo_id, commit_sha);

CREATE TABLE packages (
  id            uuid PRIMARY KEY,
  repo_id       uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  name          text NOT NULL,
  version       text,
  manifest_path text,
  UNIQUE (repo_id, name)
);

CREATE TABLE api_surfaces (
  id            uuid PRIMARY KEY,
  repo_id       uuid NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  package_id    uuid REFERENCES packages(id) ON DELETE CASCADE,
  role          text NOT NULL CHECK (role IN ('producer','consumer')),
  symbol        text NOT NULL,
  path          text,
  contract_hash text,
  meta          jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX api_surfaces_role ON api_surfaces (role, symbol);

-- ----------------------------------------------------------------- episodes

CREATE TYPE episode_status AS ENUM ('open','handed_off','in_review','closed','abandoned');

CREATE TABLE episodes (
  id             uuid PRIMARY KEY,
  namespace_id   uuid NOT NULL REFERENCES namespaces(id),
  title          text NOT NULL,
  intent         text NOT NULL,
  status         episode_status NOT NULL DEFAULT 'open',
  summary        text,
  created_by     uuid NOT NULL REFERENCES principals(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  closed_at      timestamptz,
  handed_off_to  uuid REFERENCES principals(id),
  decision_count int NOT NULL DEFAULT 0,
  dead_end_count int NOT NULL DEFAULT 0,
  acl_mode       text NOT NULL DEFAULT 'strict' CHECK (acl_mode IN ('strict','namespace')),
  embedding      vector(1024),
  fts            tsvector GENERATED ALWAYS AS (
                   to_tsvector('english', title || ' ' || intent || ' ' || coalesce(summary, ''))
                 ) STORED
);
CREATE INDEX episodes_fts ON episodes USING gin (fts);
CREATE INDEX episodes_namespace ON episodes (namespace_id, status, updated_at DESC);

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
  episode_id       uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  seq              int NOT NULL,
  what             text NOT NULL,
  why              text NOT NULL,
  options_rejected jsonb NOT NULL DEFAULT '[]',
  evidence_refs    jsonb NOT NULL DEFAULT '[]',
  created_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (episode_id, seq)
);

CREATE TABLE episode_dead_ends (
  episode_id    uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  seq           int NOT NULL,
  tried         text NOT NULL,
  outcome       text NOT NULL,
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
  state       jsonb NOT NULL DEFAULT '{}',
  synced_at   timestamptz,
  UNIQUE (episode_id, kind, external_id)
);
CREATE INDEX episode_links_external ON episode_links (kind, external_id);

CREATE TABLE materializations (
  id                   uuid PRIMARY KEY,
  episode_id           uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  requested_by         uuid NOT NULL REFERENCES principals(id),
  harness              text NOT NULL,
  agent_model          text,
  manifest             jsonb NOT NULL,
  status               text NOT NULL DEFAULT 'started' CHECK (status IN ('started','ready','failed','continued')),
  created_at           timestamptz NOT NULL DEFAULT now(),
  ready_at             timestamptz,
  first_edit_at        timestamptz,
  continued_episode_id uuid REFERENCES episodes(id)
);
CREATE INDEX materializations_episode ON materializations (episode_id);

-- -------------------------------------------------------- agent sessions

CREATE TABLE agent_sessions (
  id                    uuid PRIMARY KEY,
  principal_id          uuid NOT NULL REFERENCES principals(id),
  episode_id            uuid REFERENCES episodes(id) ON DELETE SET NULL,
  harness               text NOT NULL,
  agent_model           text,
  repo_id               uuid REFERENCES repos(id),
  git_branch            text,
  cwd_hash              bytea,
  started_at            timestamptz NOT NULL,
  ended_at              timestamptz,
  first_edit_at         timestamptz,
  tool_counts           jsonb NOT NULL DEFAULT '{}',
  files_read            int NOT NULL DEFAULT 0,
  files_edited          int NOT NULL DEFAULT 0,
  context_overhead_ratio real,
  compaction_count      int NOT NULL DEFAULT 0,
  tokens_in             bigint,
  tokens_out            bigint,
  mode                  text NOT NULL DEFAULT 'observe' CHECK (mode IN ('observe','active')),
  transcript_ref        text,
  restatement_count     int NOT NULL DEFAULT 0,
  restatement_classes   jsonb NOT NULL DEFAULT '{}',
  restatement_confidence real
);
CREATE INDEX agent_sessions_principal ON agent_sessions (principal_id, started_at DESC);
CREATE INDEX agent_sessions_repo ON agent_sessions (repo_id, started_at DESC);

CREATE TABLE session_path_signals (
  session_id uuid NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  path_hash  bytea NOT NULL,
  repo_id    uuid NOT NULL REFERENCES repos(id),
  reads      int NOT NULL DEFAULT 0,
  searches   int NOT NULL DEFAULT 0,
  edits      int NOT NULL DEFAULT 0,
  PRIMARY KEY (session_id, path_hash)
);
CREATE INDEX session_path_signals_lookup ON session_path_signals (repo_id, path_hash);

-- -------------------------------------------------------------- derivations

CREATE TYPE derivation_kind  AS ENUM ('constraint','gotcha','precedent','decision','fact');
CREATE TYPE derivation_trust AS ENUM ('unverified','verified','disputed','superseded');
CREATE TYPE validity_status  AS ENUM ('active','stale','disputed','superseded','archived');

CREATE TABLE derivations (
  id                   uuid PRIMARY KEY,
  namespace_id         uuid NOT NULL REFERENCES namespaces(id),
  kind                 derivation_kind NOT NULL,
  title                text NOT NULL,
  body_md              text NOT NULL,
  est_tokens           int NOT NULL,
  trust                derivation_trust NOT NULL DEFAULT 'unverified',
  status               validity_status NOT NULL DEFAULT 'active',
  confidence           real,
  created_by           uuid NOT NULL REFERENCES principals(id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  ttl_days             int,
  last_verified_at     timestamptz,
  verify_method        text CHECK (verify_method IN ('code_check','test','human')),
  verified_against_sha text,
  supersedes_id        uuid REFERENCES derivations(id),
  superseded_by        uuid REFERENCES derivations(id),
  embedding            vector(1024),
  fts                  tsvector GENERATED ALWAYS AS (
                         to_tsvector('english', title || ' ' || body_md)
                       ) STORED
);
CREATE INDEX derivations_fts ON derivations USING gin (fts);
CREATE INDEX derivations_namespace ON derivations (namespace_id, status, kind);

CREATE TABLE derivation_sources (
  derivation_id uuid NOT NULL REFERENCES derivations(id) ON DELETE CASCADE,
  episode_id    uuid NOT NULL REFERENCES episodes(id) ON DELETE RESTRICT,
  PRIMARY KEY (derivation_id, episode_id)
);

CREATE TABLE derivation_anchors (
  id              uuid PRIMARY KEY,
  derivation_id   uuid NOT NULL REFERENCES derivations(id) ON DELETE CASCADE,
  repo_id         uuid NOT NULL REFERENCES repos(id),
  path            text,
  symbol          text,
  content_hash    text NOT NULL,
  commit_sha      text,
  state           text NOT NULL DEFAULT 'match' CHECK (state IN ('match','drift','missing')),
  last_checked_at timestamptz,
  UNIQUE (derivation_id, repo_id, path, symbol)
);
CREATE INDEX derivation_anchors_repo ON derivation_anchors (repo_id, state);

-- ------------------------------------------------------------------ graphs

CREATE TABLE graph_edges (
  id           bigserial PRIMARY KEY,
  namespace_id uuid NOT NULL REFERENCES namespaces(id),
  src_kind     text NOT NULL CHECK (src_kind IN ('episode','repo','package','derivation','change')),
  src_id       uuid NOT NULL,
  dst_kind     text NOT NULL CHECK (dst_kind IN ('episode','repo','package','derivation','change')),
  dst_id       uuid NOT NULL,
  edge_type    text NOT NULL,
  weight       real NOT NULL DEFAULT 1.0,
  method       text,
  computed_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (src_kind, src_id, dst_kind, dst_id, edge_type)
);
CREATE INDEX graph_edges_src ON graph_edges (src_kind, src_id, edge_type, weight DESC);
CREATE INDEX graph_edges_dst ON graph_edges (dst_kind, dst_id, edge_type, weight DESC);

-- ------------------------------------------------------------------ events

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
  id                  uuid PRIMARY KEY,
  ts                  timestamptz NOT NULL,
  received_at         timestamptz NOT NULL DEFAULT now(),
  namespace_id        uuid REFERENCES namespaces(id),
  type                event_type NOT NULL,
  source              text NOT NULL DEFAULT 'client' CHECK (source IN ('client','connector','server','derived')),
  actor_id            uuid REFERENCES principals(id),
  session_id          uuid,
  episode_id          uuid,
  target_episode_id   uuid,
  target_principal_id uuid,
  repo_id             uuid REFERENCES repos(id),
  duration_ms         int,
  tokens_in           bigint,
  tokens_out          bigint,
  payload             jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX events_ns_type_ts ON events (namespace_id, type, ts DESC);
CREATE INDEX events_episode ON events (episode_id, ts DESC);
CREATE INDEX events_session ON events (session_id, ts DESC);

-- ------------------------------------------------------------- housekeeping

CREATE TABLE metrics_daily (
  day          date NOT NULL,
  namespace_id uuid NOT NULL,
  metric       text NOT NULL,
  value        jsonb NOT NULL,
  computed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (day, namespace_id, metric)
);

CREATE TABLE audit_log (
  id          bigserial PRIMARY KEY,
  ts          timestamptz NOT NULL DEFAULT now(),
  actor_id    uuid,
  action      text NOT NULL,
  object_kind text NOT NULL,
  object_id   uuid,
  meta        jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE tombstones (
  content_hash text PRIMARY KEY,
  namespace_id uuid,
  reason       text,
  deleted_at   timestamptz NOT NULL DEFAULT now()
);
