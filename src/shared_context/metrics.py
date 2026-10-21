"""First-party metric computation.

Everything here is derived from events, agent_sessions, and session_path_signals
— data the recorder emitted while doing its job. No external logs, no surveys.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row


def _round(value, digits: int = 1):
    return round(float(value), digits) if value is not None else None


def compute_report(conn: psycopg.Connection, days: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        window = "make_interval(days => %s)"

        totals = cur.execute(
            f"""
            SELECT count(*) AS sessions,
                   count(DISTINCT principal_id) AS principals,
                   count(DISTINCT repo_id) AS repos
            FROM agent_sessions
            WHERE started_at >= now() - {window}
            """,
            (days,),
        ).fetchone()

        orientation = cur.execute(
            f"""
            SELECT percentile_cont(0.5) WITHIN GROUP (
                     ORDER BY EXTRACT(EPOCH FROM (first_edit_at - started_at)) / 60.0) AS p50,
                   percentile_cont(0.9) WITHIN GROUP (
                     ORDER BY EXTRACT(EPOCH FROM (first_edit_at - started_at)) / 60.0) AS p90,
                   count(*) AS n
            FROM agent_sessions
            WHERE started_at >= now() - {window}
              AND first_edit_at IS NOT NULL
              AND first_edit_at >= started_at
            """,
            (days,),
        ).fetchone()

        rederivation = cur.execute(
            f"""
            WITH signals AS (
              SELECT sps.path_hash,
                     count(DISTINCT sps.session_id) AS sessions,
                     count(DISTINCT s.principal_id) AS principals
              FROM session_path_signals sps
              JOIN agent_sessions s ON s.id = sps.session_id
              WHERE s.started_at >= now() - {window}
              GROUP BY sps.path_hash
            )
            SELECT count(*) AS paths,
                   count(*) FILTER (WHERE sessions >= 2)  AS shared_paths,
                   count(*) FILTER (WHERE principals >= 2) AS cross_user_paths
            FROM signals
            """,
            (days,),
        ).fetchone()

        restatement = cur.execute(
            f"""
            SELECT coalesce(sum(restatement_count), 0) AS count
            FROM agent_sessions
            WHERE started_at >= now() - {window}
            """,
            (days,),
        ).fetchone()

        classes = cur.execute(
            f"""
            SELECT c.key, sum(c.value::int) AS n
            FROM agent_sessions s, jsonb_each_text(s.restatement_classes) c
            WHERE s.started_at >= now() - {window}
            GROUP BY c.key ORDER BY n DESC
            """,
            (days,),
        ).fetchall()

        overlap = cur.execute(
            f"""
            WITH signals AS (
              SELECT sps.path_hash, count(DISTINCT s.principal_id) AS principals
              FROM session_path_signals sps
              JOIN agent_sessions s ON s.id = sps.session_id
              WHERE s.started_at >= now() - interval '48 hours'
              GROUP BY sps.path_hash
            )
            SELECT count(*) FILTER (WHERE principals >= 2) AS pairs FROM signals
            """
        ).fetchone()

        tokens = cur.execute(
            f"""
            SELECT coalesce(sum(tokens_in), 0) AS tokens_in,
                   coalesce(sum(tokens_out), 0) AS tokens_out
            FROM agent_sessions
            WHERE started_at >= now() - {window}
            """,
            (days,),
        ).fetchone()

        overhead = cur.execute(
            f"""
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY context_overhead_ratio) AS median
            FROM agent_sessions
            WHERE started_at >= now() - {window}
              AND context_overhead_ratio IS NOT NULL
            """,
            (days,),
        ).fetchone()

    paths = rederivation["paths"] or 0
    shared = rederivation["shared_paths"] or 0
    cross = rederivation["cross_user_paths"] or 0

    return {
        "window_days": days,
        "session_count": totals["sessions"],
        "principal_count": totals["principals"],
        "repo_count": totals["repos"],
        "orientation_minutes": {
            "p50": _round(orientation["p50"]),
            "p90": _round(orientation["p90"]),
            "n": orientation["n"],
        },
        "rederivation": {
            "paths": paths,
            "shared_paths": shared,
            "cross_user_paths": cross,
            "within_user_rate": _round(shared / paths, 3) if paths else None,
            "cross_user_rate": _round(cross / paths, 3) if paths else None,
        },
        "restatement": {
            "count": int(restatement["count"] or 0),
            "classes": {row["key"]: int(row["n"]) for row in classes},
        },
        "overlap": {"pairs": overlap["pairs"] or 0, "window_hours": 48},
        "tokens": {"in": int(tokens["tokens_in"] or 0), "out": int(tokens["tokens_out"] or 0)},
        "overhead": {"median": _round(overhead["median"], 3)},
    }
