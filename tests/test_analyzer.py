"""Unit tests for local analysis. No server or database required."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared_context.analyzer import Signals, analyze_transcript, detect_restatement
from shared_context.repodetect import detect_repo, hash_path, normalize_path


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ------------------------------------------------------------------ restatement

def test_restatement_as_i_said() -> None:
    cls, conf = detect_restatement("as I said, we use jittered backoff", 0)
    assert cls == "as_i_said" and conf >= 0.9


def test_restatement_already_told() -> None:
    cls, _ = detect_restatement("I already told you the token lives in the vault", 2)
    assert cls == "already_told"


def test_restatement_context_dump_first_prompt() -> None:
    prompt = "We use a monorepo with our stack on Postgres. " + ("context " * 300)
    cls, conf = detect_restatement(prompt, 0)
    assert cls == "context_dump_first_prompt" and conf == 0.6


def test_restatement_clean_prompt() -> None:
    cls, conf = detect_restatement("add a retry to the payments client", 1)
    assert cls is None and conf == 0.0


# --------------------------------------------------------------------- signals

def _write_transcript(tmp: Path, root: Path) -> Path:
    t0 = datetime.now(timezone.utc)
    entries = [
        {"type": "user", "timestamp": iso(t0), "origin": {"kind": "human"},
         "message": {"content": "help me fix retry"}},
        {"type": "assistant", "timestamp": iso(t0 + timedelta(minutes=1)), "isSidechain": False,
         "message": {"usage": {"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 900},
                     "content": [
                         {"type": "tool_use", "name": "Read", "input": {"file_path": str(root / "src" / "a.py")}},
                         {"type": "tool_use", "name": "Read", "input": {"file_path": str(root / "src" / "a.py")}},
                         {"type": "tool_use", "name": "Grep", "input": {"path": str(root / "src")}},
                         {"type": "tool_use", "name": "Bash", "input": {"command": "git log --oneline"}},
                     ]}},
        {"type": "assistant", "timestamp": iso(t0 + timedelta(minutes=7)), "isSidechain": False,
         "message": {"usage": {"input_tokens": 200, "output_tokens": 30},
                     "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": str(root / "src" / "a.py")}}]}},
        {"type": "summary", "summary": "compact boundary"},
    ]
    path = tmp / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def test_signals_from_transcript(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    path = _write_transcript(tmp_path, root)

    sig = analyze_transcript(path, str(root))
    # Read x2, plus the read-only Bash (git log) reclassified as a read.
    assert sig.tool_counts["read"] == 3
    assert sig.tool_counts["search"] == 1
    assert sig.tool_counts["edit"] == 1
    assert sig.tool_counts.get("bash", 0) == 0
    assert sig.files_read == 1
    assert sig.files_edited == 1
    assert sig.tokens_in == 1200 and sig.tokens_out == 40
    assert sig.compaction_count == 1
    assert sig.first_edit_at is not None
    assert sig.context_overhead_ratio == round(4 / 5, 3)
    assert set(sig.paths) == {"src/a.py", "src"}


def test_missing_transcript_is_empty(tmp_path: Path) -> None:
    sig = analyze_transcript(tmp_path / "nope.jsonl", None)
    assert sig.tool_counts == {} and sig.first_edit_at is None


def test_signals_merge_prefers_cumulative() -> None:
    a = Signals(tool_counts={"read": 1}, restatement_count=1, restatement_classes={"as_i_said": 1})
    b = Signals(tool_counts={"read": 2}, restatement_count=2, restatement_classes={"already_told": 2})
    a.merge(b)
    assert a.tool_counts["read"] == 3
    assert a.restatement_count == 3
    assert a.restatement_classes == {"as_i_said": 1, "already_told": 2}


# ----------------------------------------------------------------- repo detection

def test_detect_repo_github(tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                    "git@github.com:acme/widgets.git"], check=True)
    ref = detect_repo(str(root))
    assert ref.forge == "github" and ref.full_name == "acme/widgets"


def test_detect_repo_local_is_hashed(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    ref = detect_repo(str(root))
    assert ref.forge == "local" and ref.full_name.startswith("local/")
    assert str(root) not in ref.full_name


def test_normalize_and_hash(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    f = root / "src" / "a.py"
    f.write_text("x")
    assert normalize_path(str(f), str(root)) == "src/a.py"
    outside = tmp_path / "other.txt"
    outside.write_text("y")
    assert normalize_path(str(outside), str(root)) == str(outside)
    assert hash_path(b"k", "src/a.py") == hash_path(b"k", "src/a.py")
    assert hash_path(b"k", "src/a.py") != hash_path(b"k", "src/b.py")
