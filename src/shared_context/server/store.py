"""Database writes for the ingest API. All functions take an open connection."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timezone

import psycopg

DEFAULT_NAMESPACE = "00000000-0000-0000-0000-000000000001"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_principal(conn: psycopg.Connection, hint: str) -> str:
    hint = hint or "p_unknown"
    row = conn.execute(
        "SELECT id FROM principals WHERE kind = 'user' AND external_id = %s", (hint,)
    ).fetchone()
    if row:
        return str(row[0])
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO principals (id, kind, external_id, display_name) VALUES (%s, 'user', %s, %s)",
        (pid, hint, hint),
    )
    return pid


def ensure_repo(conn: psycopg.Connection, forge: str, full_name: str) -> str:
    row = conn.execute(
        "SELECT id FROM repos WHERE forge = %s AND full_name = %s", (forge, full_name)
    ).fetchone()
    if row:
        return str(row[0])
    rid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO repos (id, namespace_id, forge, full_name) VALUES (%s, %s, %s, %s)",
        (rid, DEFAULT_NAMESPACE, forge, full_name),
    )
    return rid


def upsert_session(conn: psycopg.Connection, body: dict) -> dict:
    principal_id = ensure_principal(conn, body.get("principal_hint", ""))
    repo = body.get("repo") or {}
    repo_id = None
    if repo.get("full_name"):
        repo_id = ensure_repo(conn, repo.get("forge", "local"), repo["full_name"])

    cwd_hash = None
    if body.get("cwd_hash"):
        try:
            cwd_hash = base64.b64decode(body["cwd_hash"])
        except (ValueError, TypeError):
            cwd_hash = None

    conn.execute(
        """
        INSERT INTO agent_sessions
          (id, principal_id, harness, agent_model, repo_id, git_branch, cwd_hash,
           started_at, mode)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
          agent_model = COALESCE(EXCLUDED.agent_model, agent_sessions.agent_model),
          repo_id     = COALESCE(EXCLUDED.repo_id, agent_sessions.repo_id),
          git_branch  = COALESCE(EXCLUDED.git_branch, agent_sessions.git_branch),
          mode        = EXCLUDED.mode
        """,
        (
            body["id"],
            principal_id,
            body.get("harness", "unknown"),
            body.get("agent_model"),
            repo_id,
            repo.get("branch"),
            cwd_hash,
            body.get("started_at"),
            body.get("mode", "observe"),
        ),
    )
    return {"session_id": body["id"], "principal_id": principal_id, "repo_id": repo_id}


def upsert_signals(conn: psycopg.Connection, session_id: str, body: dict) -> None:
    s = body.get("signals") or {}
    tokens = s.get("tokens") or {}
    restatement = s.get("restatement") or {}
    row = conn.execute(
        "SELECT repo_id, principal_id FROM agent_sessions WHERE id = %s", (session_id,)
    ).fetchone()
    if row is None:
        raise KeyError(session_id)
    repo_id, principal_id = row[0], row[1]

    conn.execute(
        """
        UPDATE agent_sessions SET
          ended_at = COALESCE(%s, ended_at),
          first_edit_at = COALESCE(%s, first_edit_at),
          tool_counts = %s,
          files_read = %s,
          files_edited = %s,
          context_overhead_ratio = %s,
          compaction_count = %s,
          tokens_in = %s,
          tokens_out = %s,
          restatement_count = %s,
          restatement_classes = %s,
          restatement_confidence = %s
        WHERE id = %s
        """,
        (
            body.get("ended_at"),
            s.get("first_edit_at"),
            psycopg.types.json.Json(s.get("tool_counts") or {}),
            s.get("files_read", 0),
            s.get("files_edited", 0),
            s.get("context_overhead_ratio"),
            s.get("compaction_count", 0),
            tokens.get("in", 0),
            tokens.get("out", 0),
            restatement.get("count", 0),
            psycopg.types.json.Json(restatement.get("classes") or {}),
            restatement.get("confidence"),
            session_id,
        ),
    )

    for ps in body.get("path_signals") or []:
        try:
            digest = base64.b64decode(ps["hash"])
        except (KeyError, ValueError, TypeError):
            continue
        conn.execute(
            """
            INSERT INTO session_path_signals (session_id, path_hash, repo_id, reads, searches, edits)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id, path_hash) DO UPDATE SET
              reads = EXCLUDED.reads, searches = EXCLUDED.searches, edits = EXCLUDED.edits
            """,
            (
                session_id,
                digest,
                repo_id,
                ps.get("reads", 0),
                ps.get("searches", 0),
                ps.get("edits", 0),
            ),
        )


def insert_events(conn: psycopg.Connection, events: list[dict]) -> int:
    inserted = 0
    for event in events:
        try:
            session_id = event.get("session_id")
            actor_id = repo_id = None
            if session_id:
                row = conn.execute(
                    "SELECT principal_id, repo_id FROM agent_sessions WHERE id = %s", (session_id,)
                ).fetchone()
                if row:
                    actor_id, repo_id = row[0], row[1]
            ts = event.get("ts")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            cur = conn.execute(
                """
                INSERT INTO events
                  (id, ts, namespace_id, type, source, actor_id, session_id, episode_id,
                   repo_id, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    event["id"],
                    ts or utcnow(),
                    DEFAULT_NAMESPACE,
                    event["type"],
                    event.get("source", "client"),
                    actor_id,
                    session_id,
                    event.get("episode_id"),
                    repo_id,
                    psycopg.types.json.Json(event.get("payload") or {}),
                ),
            )
            inserted += cur.rowcount or 0
        except (psycopg.Error, KeyError, ValueError):
            continue
    return inserted


def repo_path_key(conn: psycopg.Connection, forge: str, full_name: str, secret: str) -> str:
    """Stable per-repo HMAC key. Clients hash paths with this; the server never
    stores a path."""
    digest = hmac.new(
        secret.encode("utf-8"), f"{forge}:{full_name}".encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode()
