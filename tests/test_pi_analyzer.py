"""pi harness tests: session-tree parsing and extension install/uninstall."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared_context.harnesses import get, names
from shared_context.harnesses.pi import (
    PI_MARKER,
    active_chain,
    extension_path,
    install_pi,
    parse_pi_session,
    uninstall_pi,
)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_session(tmp: Path, root: Path) -> Path:
    t0 = datetime.now(timezone.utc)
    entries = [
        {"type": "session", "version": 3, "id": "sess", "timestamp": iso(t0), "cwd": str(root)},
        {
            "type": "message", "id": "a1", "parentId": None, "timestamp": iso(t0),
            "message": {"role": "user", "content": [{"type": "text", "text": "as I said, we use jittered backoff"}]},
        },
        {
            "type": "message", "id": "a2", "parentId": "a1", "timestamp": iso(t0 + timedelta(minutes=1)),
            "message": {
                "role": "assistant",
                "usage": {"input": 100, "output": 10, "cacheRead": 900, "cacheWrite": 0, "totalTokens": 1010},
                "content": [
                    {"type": "text", "text": "let me look"},
                    {"type": "toolCall", "id": "t1", "name": "read", "arguments": {"path": str(root / "src" / "a.py")}},
                    {"type": "toolCall", "id": "t2", "name": "bash", "arguments": {"command": "cat src/a.py"}},
                    {"type": "toolCall", "id": "t3", "name": "grep", "arguments": {"pattern": "retry", "path": str(root / "src")}},
                ],
            },
        },
        # abandoned branch: read a path the active session never used
        {
            "type": "message", "id": "b1", "parentId": "a2", "timestamp": iso(t0 + timedelta(minutes=5)),
            "message": {"role": "assistant", "content": [
                {"type": "toolCall", "id": "t9", "name": "read", "arguments": {"path": str(root / "src" / "secret.py")}},
            ]},
        },
        {
            "type": "message", "id": "a3", "parentId": "a2", "timestamp": iso(t0 + timedelta(minutes=7)),
            "message": {
                "role": "assistant",
                "usage": {"input": 200, "output": 20, "cacheRead": 0, "cacheWrite": 0},
                "content": [
                    {"type": "toolCall", "id": "t4", "name": "edit",
                     "arguments": {"path": str(root / "src" / "a.py"), "oldText": "x", "newText": "y"}},
                ],
            },
        },
        {"type": "compaction", "id": "c1", "parentId": "a3", "timestamp": iso(t0 + timedelta(minutes=9)),
         "summary": "compacted", "firstKeptEntryId": "a2", "tokensBefore": 50000},
    ]
    path = tmp / "pi-session.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def test_pi_signals(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    path = write_session(tmp_path, root)

    sig = parse_pi_session(path, str(root))
    assert sig.prompts == 1
    assert sig.restatement_count == 1
    assert sig.restatement_classes == {"as_i_said": 1}
    # read tool (1) + read-only bash cat (1)
    assert sig.tool_counts["read"] == 2
    assert sig.tool_counts["search"] == 1
    assert sig.tool_counts["edit"] == 1
    assert sig.files_read == 1
    assert sig.files_edited == 1
    assert sig.tokens_in == 1200 and sig.tokens_out == 30
    assert sig.compaction_count == 1
    assert sig.context_overhead_ratio == 0.75
    assert set(sig.paths) == {"src/a.py", "src"}
    assert "secret.py" not in json.dumps(sig.paths)
    assert sig.first_edit_at is not None


def test_active_chain_excludes_abandoned_branch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    path = write_session(tmp_path, root)
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    chain_ids = [e["id"] for e in active_chain(entries)]
    assert "b1" not in chain_ids
    assert chain_ids == ["a1", "a2", "a3", "c1"]


def test_legacy_session_without_ids(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    path = tmp_path / "legacy.jsonl"
    entries = [
        {"type": "session", "version": 1},
        {"type": "message", "message": {"role": "user", "content": "plain prompt"}},
        {"type": "message", "message": {"role": "assistant", "content": [
            {"type": "toolCall", "name": "write", "arguments": {"path": str(root / "b.py"), "content": "x"}}]}},
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    sig = parse_pi_session(path, str(root))
    assert sig.prompts == 1
    assert sig.files_edited == 1
    assert sig.paths == {"b.py": {"reads": 0, "searches": 0, "edits": 1}}


def test_extension_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert get("pi").name == "pi"
    assert "pi" in names()

    path = install_pi("observe")
    assert path == extension_path()
    text = path.read_text()
    assert PI_MARKER in text
    assert '"hook"' in text and "session_start" in text and "session_shutdown" in text
    assert get("pi").is_installed()

    removed = uninstall_pi()
    assert removed == path
    assert not path.exists()

    # a foreign file with the same name must survive uninstall
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// someone else's extension\n")
    assert uninstall_pi() is None
    assert path.exists()


def test_install_pi_rejects_active(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    try:
        install_pi("active")
    except ValueError as exc:
        assert "observe" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("active mode must be rejected until Phase 1")
