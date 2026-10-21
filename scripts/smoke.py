"""End-to-end smoke test: two users, one repo, one learned constraint.

Simulates Claude Code hook payloads against a running server, then asserts the
first-party metrics come out right.

    uv run python scripts/smoke.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SERVER = os.environ.get("CTX_SERVER_URL", "http://127.0.0.1:8787")
TOKEN = os.environ.get("CTX_TOKEN", "dev-token")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_transcript(path: Path, root: Path, t0: datetime, first_prompt: str, reads: list[str], edit_after_min: int) -> None:
    lines = [
        {"type": "user", "timestamp": iso(t0), "origin": {"kind": "human"},
         "message": {"role": "user", "content": first_prompt}},
        {"type": "assistant", "timestamp": iso(t0 + timedelta(minutes=1)), "isSidechain": False,
         "message": {"role": "assistant", "usage": {"input_tokens": 1200, "output_tokens": 40, "cache_read_input_tokens": 5000},
                     "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": str(root / p)}}
                                 for p in reads]}},
        {"type": "assistant", "timestamp": iso(t0 + timedelta(minutes=edit_after_min)), "isSidechain": False,
         "message": {"role": "assistant", "usage": {"input_tokens": 3000, "output_tokens": 200},
                     "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": str(root / reads[0])}}]}},
        {"type": "summary", "summary": "compacted"},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def run_hook(event: str, payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "shared_context.cli", "hook", event],
        input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=60,
    )


def main() -> int:
    import uuid as _uuid

    import httpx

    run_id = _uuid.uuid4().hex[:6]
    headers = {"Authorization": f"Bearer {TOKEN}"}
    baseline = httpx.get(f"{SERVER}/v1/report", params={"days": 1}, headers=headers, timeout=10).json()

    tmp = Path(tempfile.mkdtemp(prefix="ctx-smoke-"))
    root = tmp / "repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("def retry(): ...\n")
    (root / "src" / "b.py").write_text("TIMEOUT = 5\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                    f"https://github.com/acme/widgets-{run_id}.git"], check=True)

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")

    for user, first_prompt, edit_after in [
        (f"alice{run_id}", "as I said, we use jittered backoff on the payments client", 6),
        (f"bob{run_id}", "help me add retry to the payments client", 2),
    ]:
        state = tmp / f"state-{user}"
        env = {
            **os.environ,
            "CTX_STATE_DIR": str(state),
            "CTX_CONFIG_DIR": str(tmp / f"config-{user}"),
            "CTX_PRINCIPAL": f"p_{user}",
            "CTX_SERVER_URL": SERVER,
            "CTX_TOKEN": TOKEN,
        }
        t0 = datetime.now(timezone.utc)
        transcript = tmp / f"{user}.jsonl"
        write_transcript(transcript, root, t0, first_prompt, ["src/a.py", "src/b.py"], edit_after)
        session_id = f"sess-{user}"
        base = {"session_id": session_id, "cwd": str(root), "transcript_path": str(transcript)}

        r = run_hook("session-start", base, env)
        check(f"{user}: session-start exits 0", r.returncode == 0, r.stderr.strip()[:120])
        r = run_hook("user-prompt-submit", {**base, "prompt": first_prompt}, env)
        check(f"{user}: prompt hook exits 0", r.returncode == 0, r.stderr.strip()[:120])
        r = run_hook("stop", base, env)
        check(f"{user}: stop hook exits 0", r.returncode == 0, r.stderr.strip()[:120])
        r = run_hook("session-end", {**base, "reason": "exit"}, env)
        check(f"{user}: session-end exits 0", r.returncode == 0, r.stderr.strip()[:120])

    import httpx

    report = httpx.get(f"{SERVER}/v1/report", params={"days": 1},
                       headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10).json()
    print("\nreport:", json.dumps(report, indent=2))

    delta_sessions = report["session_count"] - baseline["session_count"]
    delta_principals = report["principal_count"] - baseline["principal_count"]
    delta_orientation = (report["orientation_minutes"]["n"] or 0) - (baseline["orientation_minutes"]["n"] or 0)
    delta_paths = report["rederivation"]["paths"] - baseline["rederivation"]["paths"]
    delta_cross = report["rederivation"]["cross_user_paths"] - baseline["rederivation"]["cross_user_paths"]
    delta_restate = report["restatement"]["count"] - baseline["restatement"]["count"]

    check("two sessions recorded this run", delta_sessions == 2, str(delta_sessions))
    check("two new principals", delta_principals == 2, str(delta_principals))
    check("orientation measured for both", delta_orientation == 2, str(delta_orientation))
    check("orientation p50 in range", 1 <= (report["orientation_minutes"]["p50"] or 0) <= 8,
          str(report["orientation_minutes"]["p50"]))
    check("two paths hashed", delta_paths == 2, str(delta_paths))
    check("cross-user re-derivation found", delta_cross == 2, str(delta_cross))
    check("restatement detected", delta_restate == 1, str(delta_restate))
    check("raw path never stored", "src/a.py" not in json.dumps(report))

    failed = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed · artifacts in {tmp}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
