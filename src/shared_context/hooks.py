"""Harness hook handlers.

Every handler obeys three rules: fail open, stay fast, and never write to
stdout unless the harness is supposed to inject something (observe mode writes
nothing). Raw prompt text and raw paths never leave this process.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import analyzer, spool
from .analyzer import Signals
from .client import Client
from .config import Config, state_dir
from .harnesses import HARNESSES, get as get_harness
from .ids import uuid7_str
from .repodetect import RepoRef, cwd_hash, detect_repo, hash_path, normalize_path, repo_key


# --------------------------------------------------------------- local state

def _state_file(name: str) -> Path:
    return state_dir() / name


def _load(name: str, default):
    p = _state_file(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except ValueError:
        return default


def _save(name: str, data) -> None:
    p = _state_file(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ----------------------------------------------------------------- helpers

def transcript_path_for(payload: dict, cwd: str, harness_session_id: str) -> str | None:
    explicit = payload.get("transcript_path") or payload.get("transcriptPath")
    if explicit and Path(explicit).exists():
        return explicit
    # Claude Code convention: ~/.claude/projects/<cwd with / and . replaced by ->/<session>.jsonl
    encoded = re.sub(r"[/.]", "-", cwd)
    candidate = Path.home() / ".claude" / "projects" / encoded / f"{harness_session_id}.jsonl"
    return str(candidate) if candidate.exists() else None


def _ensure_session(config: Config, payload: dict) -> dict:
    """Find or create the local session record; returns {"ctx_id", ...}."""
    harness = str(payload.get("harness") or "claude-code")
    if harness not in HARNESSES:
        harness = "claude-code"
    harness_id = str(payload.get("session_id") or payload.get("sessionId") or uuid.uuid4().hex)
    cwd = str(payload.get("cwd") or os.getcwd())
    ref = detect_repo(cwd)
    sessions = _load("sessions.json", {})
    session_key = f"{harness}:{harness_id}"
    record = sessions.get(session_key)
    if record and record.get("ctx_id"):
        record.setdefault("ents", {})
        return record

    record = {
        "ctx_id": uuid7_str(),
        "key": session_key,
        "harness_id": harness_id,
        "harness": harness,
        "started_at": _now(),
        "cwd": cwd,
        "root": ref.root,
        "repo": _repo_payload(ref, cwd),
        "repo_key": repo_key(ref),
        "first_edit_sent": False,
        "transcript": None,
    }
    sessions[session_key] = record
    _save("sessions.json", sessions)

    client = Client(config)
    client.post(
        "/v1/sessions",
        {
            "id": record["ctx_id"],
            "principal_hint": config.principal,
            "harness": record["harness"],
            "started_at": record["started_at"],
            "mode": config.mode,
            "repo": record["repo"],
            "cwd_hash": base64.b64encode(cwd_hash(ref.root or cwd)).decode(),
        },
        key=record["ctx_id"],
    )
    _emit(config, record["ctx_id"], "session.started", {"harness": record["harness"]})
    return record


def _emit(config: Config, session_id: str, event_type: str, payload: dict | None = None) -> None:
    event = {
        "id": uuid7_str(),
        "ts": _now(),
        "type": event_type,
        "source": "client",
        "session_id": session_id,
        "payload": payload or {},
    }
    Client(config).post(f"/v1/sessions/{session_id}/events", {"events": [event]})


def _path_key(config: Config, ref: RepoRef) -> bytes | None:
    """Per-repo HMAC key, cached locally. Never the raw path leaves."""
    key_id = repo_key(ref)
    cache = _load("pathkeys.json", {})
    entry = cache.get(key_id)
    if entry and entry.get("key"):
        return base64.b64decode(entry["key"])
    resp = Client(config).get("/v1/path-key", {"repo": key_id})
    if not resp or not resp.get("key"):
        return None
    cache[key_id] = {"key": resp["key"], "fetched_at": _now()}
    _save("pathkeys.json", cache)
    return base64.b64decode(resp["key"])


def _signals_payload(sig: Signals, path_key: bytes | None, ref: RepoRef) -> dict:
    signals = {
        "tool_counts": sig.tool_counts,
        "files_read": sig.files_read,
        "files_edited": sig.files_edited,
        "context_overhead_ratio": sig.context_overhead_ratio,
        "compaction_count": sig.compaction_count,
        "tokens": {"in": sig.tokens_in, "out": sig.tokens_out},
        "first_edit_at": sig.first_edit_at,
        "restatement": {
            "count": sig.restatement_count,
            "classes": sig.restatement_classes,
            "confidence": sig.restatement_confidence,
        },
    }
    path_signals = []
    if path_key is not None:
        for normalized, counters in sig.paths.items():
            if not any(counters.values()):
                continue
            path_signals.append(
                {
                    "hash": base64.b64encode(hash_path(path_key, normalized)).decode(),
                    "repo": repo_key(ref),
                    "reads": counters.get("reads", 0),
                    "searches": counters.get("searches", 0),
                    "edits": counters.get("edits", 0),
                }
            )
    return {"signals": signals, "path_signals": path_signals}


# ------------------------------------------------------------------ handlers

def session_start(config: Config, payload: dict) -> str | None:
    record = _ensure_session(config, payload)
    if config.mode == "active":
        pack = Client(config).post(
            "/v1/context-pack",
            {
                "session_id": record["ctx_id"],
                "repo": record["repo"],
                "budget_tokens": 4000,
            },
        )
        if pack and pack.get("rendered"):
            return json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": pack["rendered"],
                    }
                }
            )
    return None


def user_prompt_submit(config: Config, payload: dict) -> str | None:
    record = _ensure_session(config, payload)
    prompt = str(payload.get("prompt") or payload.get("user_prompt") or "")
    pending = _load(f"pending-{record['ctx_id']}.json", {"prompts": 0})
    cls, conf = analyzer.detect_restatement(prompt, int(pending.get("prompts", 0)))
    pending["prompts"] = int(pending.get("prompts", 0)) + 1
    if cls:
        pending["restatement_count"] = int(pending.get("restatement_count", 0)) + 1
        classes = pending.setdefault("restatement_classes", {})
        classes[cls] = classes.get(cls, 0) + 1
        pending["confidence"] = max(float(pending.get("confidence", 0.0)), conf)
    pending["updated_at"] = _now()
    _save(f"pending-{record['ctx_id']}.json", pending)
    return None


def pre_compact(config: Config, payload: dict) -> str | None:
    record = _ensure_session(config, payload)
    cwd = record.get("cwd") or os.getcwd()
    path = transcript_path_for(payload, cwd, record["harness_id"])
    size = Path(path).stat().st_size if path and Path(path).exists() else 0
    pending = _load(f"pending-{record['ctx_id']}.json", {})
    pending["compactions"] = int(pending.get("compactions", 0)) + 1
    pending["last_snapshot_bytes"] = size
    pending["updated_at"] = _now()
    _save(f"pending-{record['ctx_id']}.json", pending)
    _emit(
        config,
        record["ctx_id"],
        "session.compacted",
        {
            "trigger": payload.get("trigger", "auto"),
            "compaction_index": pending["compactions"],
            "transcript_bytes": size,
            # Transcript bodies are only uploaded when policy allows; the
            # episode must remain useful without them.
            "transcript_uploaded": False,
        },
    )
    return None


def stop(config: Config, payload: dict) -> str | None:
    """Runs at the end of every assistant turn: recompute and update signals."""
    record = _ensure_session(config, payload)
    return _update_signals(config, record, payload, ended=False)


def session_end(config: Config, payload: dict) -> str | None:
    record = _ensure_session(config, payload)
    return _update_signals(config, record, payload, ended=True)


def _repo_payload(ref: RepoRef, root: str) -> dict:
    return {"forge": ref.forge, "full_name": ref.full_name, "branch": ref.branch}


def _update_signals(config: Config, record: dict, payload: dict, ended: bool) -> str | None:
    cwd = record.get("cwd") or os.getcwd()
    transcript = transcript_path_for(payload, cwd, record["harness_id"])
    ref = RepoRef(
        forge=record["repo"]["forge"],
        full_name=record["repo"]["full_name"],
        root=record.get("root"),
        branch=record["repo"].get("branch"),
    )

    harness = get_harness(record.get("harness"))
    sig = harness.parse(transcript, record.get("root"), record.get("cwd")) if transcript else Signals()
    pending = _load(f"pending-{record['ctx_id']}.json", {})
    if sig.prompts == 0 and pending.get("restatement_count"):
        # Transcript unavailable: fall back to the locally accumulated counts.
        sig.restatement_count = int(pending.get("restatement_count", 0))
        sig.restatement_classes = pending.get("restatement_classes", {})
        sig.restatement_confidence = float(pending.get("confidence", 0.0))

    path_key = _path_key(config, ref) if config.path_signals else None
    body = _signals_payload(sig, path_key, ref)
    body["ended"] = ended
    if ended:
        body["ended_at"] = _now()

    Client(config).post(f"/v1/sessions/{record['ctx_id']}/signals", body, key=record["ctx_id"])

    if sig.first_edit_at and not record.get("first_edit_sent"):
        _emit(
            config,
            record["ctx_id"],
            "session.first_edit",
            {"first_edit_at": sig.first_edit_at, "harness": record.get("harness")},
        )
        sessions = _load("sessions.json", {})
        if record["key"] in sessions:
            sessions[record["key"]]["first_edit_sent"] = True
            _save("sessions.json", sessions)

    if ended:
        _emit(config, record["ctx_id"], "session.ended", {"reason": payload.get("reason")})
        sessions = _load("sessions.json", {})
        sessions.pop(record["key"], None)
        _save("sessions.json", sessions)
        _state_file(f"pending-{record['ctx_id']}.json").unlink(missing_ok=True)

    Client(config).flush(limit=50)
    return None


HANDLERS = {
    "session-start": session_start,
    "session_start": session_start,
    "user-prompt-submit": user_prompt_submit,
    "user_prompt_submit": user_prompt_submit,
    "pre-compact": pre_compact,
    "pre_compact": pre_compact,
    "stop": stop,
    "session-end": session_end,
    "session_end": session_end,
}


def handle(event: str, payload: dict, config: Config) -> str | None:
    fn = HANDLERS.get(event)
    if fn is None:
        raise SystemExit(f"unknown hook event: {event}")
    return fn(config, payload)
