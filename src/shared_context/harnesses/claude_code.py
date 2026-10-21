"""Claude Code adapter: settings.json hooks + JSONL transcript parser."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from ..analyzer import Signals, analyze_transcript
from ..install import hook_command
from .base import Harness

HOOK_EVENTS = ["SessionStart", "UserPromptSubmit", "PreCompact", "Stop", "SessionEnd"]
MARKER = "shared_context.cli hook"
EVENT_SLUGS = {
    "SessionStart": "session-start",
    "UserPromptSubmit": "user-prompt-submit",
    "PreCompact": "pre-compact",
    "Stop": "stop",
    "SessionEnd": "session-end",
}


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _is_ours(entry: dict) -> bool:
    for hook in entry.get("hooks") or []:
        command = str(hook.get("command", ""))
        if MARKER in command or "ctx hook" in command:
            return True
    return False


def install_claude_code(mode: str) -> Path:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(f".json.bak.{int(time.time())}")
        shutil.copy2(path, backup)
        settings = json.loads(path.read_text() or "{}")
    else:
        settings = {}
    hooks = settings.setdefault("hooks", {})
    for event in HOOK_EVENTS:
        entries = [e for e in hooks.get(event, []) if not _is_ours(e)]
        entries.append(
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command(EVENT_SLUGS[event]),
                        "timeout": 30 if event in ("Stop", "SessionEnd") else 10,
                    }
                ],
            }
        )
        hooks[event] = entries
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def uninstall_claude_code() -> Path | None:
    path = settings_path()
    if not path.exists():
        return None
    settings = json.loads(path.read_text() or "{}")
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        hooks[event] = [e for e in hooks[event] if not _is_ours(e)]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


class ClaudeCodeHarness(Harness):
    name = "claude-code"
    label = "Claude Code"
    doc_preference = "CLAUDE.md"
    supports_active = True

    def install(self, mode: str) -> list[Path]:
        return [install_claude_code(mode)]

    def uninstall(self) -> list[Path]:
        path = uninstall_claude_code()
        return [path] if path else []

    def is_installed(self) -> bool:
        path = settings_path()
        if not path.exists():
            return False
        try:
            hooks = json.loads(path.read_text()).get("hooks", {})
        except ValueError:
            return False
        return any(_is_ours(entry) for entries in hooks.values() for entry in entries)

    def _parse(self, transcript: str | Path, root: str | None, cwd: str | None) -> Signals:
        return analyze_transcript(transcript, root, cwd)
