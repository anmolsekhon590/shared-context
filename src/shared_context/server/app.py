"""ctxd — ingest + report API.

Synchronous FastAPI endpoints backed by a psycopg connection pool; FastAPI runs
them in its threadpool. Auth is a single bearer token in Phase 0.
"""

from __future__ import annotations

import os

import psycopg
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .. import db
from ..config import db_url, path_key_secret
from ..metrics import compute_report
from . import store

API_TOKEN = os.environ.get("CTX_API_TOKEN", "dev-token")

app = FastAPI(title="ctxd", version="0.0.1")
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = db.pool(db_url())
    return _pool


def auth(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    return token


def _conn():
    with get_pool().connection() as conn:
        yield conn


@app.get("/healthz")
def healthz() -> dict:
    try:
        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
        return {"ok": True, "db": True}
    except psycopg.Error:
        return {"ok": False, "db": False}


@app.get("/v1/capabilities")
def capabilities() -> dict:
    return {
        "schema_versions": [1],
        "features": ["observe", "ingest", "signals", "path_key", "report"],
        "modes": ["observe", "active"],
        "limits": {"event_batch": 500, "payload_bytes": 1_048_576, "path_signals": 2000},
    }


@app.post("/v1/sessions")
def post_session(body: dict, conn: psycopg.Connection = Depends(_conn), _: str = Depends(auth)) -> dict:
    if not body.get("id"):
        raise HTTPException(status_code=422, detail="id is required")
    result = store.upsert_session(conn, body)
    return {"ok": True, **result}


@app.post("/v1/sessions/{session_id}/events")
def post_events(
    session_id: str,
    body: dict,
    conn: psycopg.Connection = Depends(_conn),
    _: str = Depends(auth),
) -> dict:
    events = body.get("events") or []
    if len(events) > 500:
        raise HTTPException(status_code=413, detail="event batch too large")
    for event in events:
        event.setdefault("session_id", session_id)
    inserted = store.insert_events(conn, events)
    return {"ok": True, "received": len(events), "inserted": inserted}


@app.post("/v1/sessions/{session_id}/signals")
def post_signals(
    session_id: str,
    body: dict,
    conn: psycopg.Connection = Depends(_conn),
    _: str = Depends(auth),
) -> dict:
    try:
        store.upsert_signals(conn, session_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown session; POST /v1/sessions first")
    return {"ok": True, "path_signals": len(body.get("path_signals") or [])}


@app.get("/v1/path-key")
def get_path_key(
    repo: str = Query(..., description="forge:owner/name"),
    conn: psycopg.Connection = Depends(_conn),
    _: str = Depends(auth),
) -> dict:
    if ":" not in repo:
        raise HTTPException(status_code=422, detail="repo must be forge:owner/name")
    forge, full_name = repo.split(":", 1)
    store.ensure_repo(conn, forge, full_name)
    return {"repo": repo, "key": store.repo_path_key(conn, forge, full_name, path_key_secret())}


@app.post("/v1/context-pack")
def context_pack(body: dict, _: str = Depends(auth)) -> dict:
    # Observe mode deliberately injects nothing. Active mode ships with retrieval.
    if body.get("mode", "observe") != "active":
        return {
            "schema_version": 1,
            "mode": "observe",
            "no_context_found": True,
            "reason": "observe_mode",
            "rendered": "",
            "pack": None,
        }
    return {
        "schema_version": 1,
        "mode": "active",
        "no_context_found": True,
        "reason": "retrieval_not_implemented",
        "rendered": "",
        "pack": None,
    }


@app.get("/v1/report")
def report(
    days: int = Query(7, ge=1, le=365),
    conn: psycopg.Connection = Depends(_conn),
    _: str = Depends(auth),
) -> dict:
    return compute_report(conn, days)


@app.get("/v1/sessions/{session_id}")
def get_session(
    session_id: str, conn: psycopg.Connection = Depends(_conn), _: str = Depends(auth)
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT * FROM agent_sessions WHERE id = %s", (session_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    # bytea columns (cwd_hash) are not JSON-serializable; expose them as hex.
    return {
        key: bytes(value).hex() if isinstance(value, (bytes, bytearray, memoryview)) else value
        for key, value in row.items()
    }


@app.exception_handler(psycopg.Error)
async def db_error_handler(request: Request, exc: psycopg.Error) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "database error", "error": str(exc)})


def run(host: str = "127.0.0.1", port: int = 8787, reload: bool = False) -> None:
    if os.environ.get("CTX_AUTO_MIGRATE", "1") == "1":
        applied = db.migrate(db_url())
        if applied:
            print(f"applied migrations: {', '.join(applied)}")
    uvicorn.run("shared_context.server.app:app", host=host, port=port, reload=reload)
