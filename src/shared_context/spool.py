"""Local spool: hook payloads are queued here when the server is unreachable."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .config import state_dir

SPOOL_NAME = "spool.jsonl"


def spool_path() -> Path:
    return state_dir() / SPOOL_NAME


def append(method: str, path: str, payload: dict, key: str | None = None) -> None:
    entry = {
        "id": str(uuid.uuid4()),
        "method": method,
        "path": path,
        "payload": payload,
        "key": key,
        "queued_at": time.time(),
    }
    p = spool_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def read_all() -> list[dict]:
    p = spool_path()
    if not p.exists():
        return []
    entries: list[dict] = []
    with p.open("r", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    return entries


def rewrite(entries: list[dict]) -> None:
    p = spool_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    os.replace(tmp, p)


def size() -> int:
    p = spool_path()
    if not p.exists():
        return 0
    with p.open("r", errors="replace") as fh:
        return sum(1 for line in fh if line.strip())
