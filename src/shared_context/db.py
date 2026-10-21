"""Postgres access and migration runner."""

from __future__ import annotations

import pathlib

import psycopg

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def connect(db_url: str) -> psycopg.Connection:
    conn = psycopg.connect(db_url, autocommit=True)
    return conn


def migrate(db_url: str) -> list[str]:
    """Apply pending SQL migrations in filename order. Idempotent."""
    applied: list[str] = []
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    with connect(db_url) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version     text PRIMARY KEY,
              applied_at  timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            if version in done:
                continue
            sql = path.read_text()
            try:
                conn.execute(sql)
            except psycopg.Error:
                # Fallback for drivers using the extended protocol: split on
                # statement boundaries. Simple, not a full SQL parser.
                conn.execute("BEGIN")
                for stmt in _split(sql):
                    conn.execute(stmt)
                conn.execute("COMMIT")
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied.append(version)
    return applied


def _split(sql: str) -> list[str]:
    stmts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    for line in sql.splitlines():
        if line.count("$$") % 2 == 1:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";") and not line.strip().startswith("--"):
            stmt = "\n".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def pool(db_url: str, min_size: int = 1, max_size: int = 8):
    """Lazily create a connection pool (server only)."""
    from psycopg_pool import ConnectionPool

    return ConnectionPool(db_url, min_size=min_size, max_size=max_size, open=True)
