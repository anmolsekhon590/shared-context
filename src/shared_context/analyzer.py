"""Local transcript analysis.

Everything in this module runs on the developer's machine. Only aggregates
leave it: counts, timestamps, token totals, and HMACs of paths. Prompt text is
never transmitted, and restatement detection is deliberately rule-based so the
result is explainable and auditable.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TOOL_CATEGORY = {
    "Read": "read",
    "Edit": "edit",
    "Write": "edit",
    "NotebookEdit": "edit",
    "Bash": "bash",
    "Grep": "search",
    "Glob": "search",
    "WebFetch": "web",
    "WebSearch": "web",
}

MAX_TRANSCRIPT_BYTES = 20 * 1024 * 1024

BASH_PATH_COMMANDS = {"cat", "head", "tail", "wc", "file", "tree", "ls", "find", "bat", "less", "more"}
BASH_SEARCH_COMMANDS = {"rg", "grep", "ag", "ack"}
BASH_READ_ONLY_RE = re.compile(
    r"^\s*(ls|cat|head|tail|rg|grep|find|git (log|show|diff|status|branch)|wc|tree|file|bat|less|more|ag|ack)\b"
)
CANONICAL_PATH_KEYS = {"read": "reads", "edit": "edits", "search": "searches"}

# Conservative, explainable restatement rules. No model, no prompt text stored.
RESTATEMENT_RULES: list[tuple[str, re.Pattern, float]] = [
    ("as_i_said", re.compile(r"\b(as|like) (i|we) (said|mentioned|discussed|talked about)\b", re.I), 0.9),
    ("already_told", re.compile(r"\bi (already|just) (told|explained|showed) (you|it)\b", re.I), 0.9),
    ("again", re.compile(r"\b(remind|tell|explain|say) (you |me )?again\b|\bagain,? (the|this|our|we|i)\b", re.I), 0.7),
]
CONTEXT_DUMP_HINTS = re.compile(
    r"\b(we use|our stack|this repo|the repo uses|our conventions|the architecture|our setup|"
    r"the api works|the codebase)\b",
    re.I,
)


@dataclass
class Signals:
    tool_counts: dict[str, int] = field(default_factory=dict)
    files_read: int = 0
    files_edited: int = 0
    context_overhead_ratio: float | None = None
    compaction_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    first_edit_at: str | None = None
    paths: dict[str, dict[str, int]] = field(default_factory=dict)  # normalized -> counters
    restatement_count: int = 0
    restatement_classes: dict[str, int] = field(default_factory=dict)
    restatement_confidence: float = 0.0
    prompts: int = 0

    def merge(self, other: "Signals") -> None:
        self.tool_counts = dict(Counter(self.tool_counts) + Counter(other.tool_counts))
        self.files_read = max(self.files_read, other.files_read)
        self.files_edited = max(self.files_edited, other.files_edited)
        self.compaction_count = max(self.compaction_count, other.compaction_count)
        self.tokens_in = max(self.tokens_in, other.tokens_in)
        self.tokens_out = max(self.tokens_out, other.tokens_out)
        self.first_edit_at = self.first_edit_at or other.first_edit_at
        self.restatement_count += other.restatement_count
        self.restatement_classes = dict(
            Counter(self.restatement_classes) + Counter(other.restatement_classes)
        )
        self.restatement_confidence = max(self.restatement_confidence, other.restatement_confidence)
        self.prompts = max(self.prompts, other.prompts)
        for path, counters in other.paths.items():
            cur = self.paths.setdefault(path, {"reads": 0, "searches": 0, "edits": 0})
            for k, v in counters.items():
                cur[k] = max(cur[k], v)
        self._ratio()

    def _ratio(self) -> None:
        explore = self.tool_counts.get("read", 0) + self.tool_counts.get("search", 0) + self.tool_counts.get("web", 0)
        mutate = self.tool_counts.get("edit", 0)
        if explore + mutate > 0:
            self.context_overhead_ratio = round(explore / (explore + mutate), 3)


def detect_restatement(text: str, prompt_index: int) -> tuple[str | None, float]:
    """Return (class, confidence) for one prompt, or (None, 0)."""
    if not text:
        return None, 0.0
    for name, rx, weight in RESTATEMENT_RULES:
        if rx.search(text):
            return name, weight
    approx_tokens = len(text) / 4
    if approx_tokens > 200 and CONTEXT_DUMP_HINTS.search(text):
        return ("context_dump_first_prompt" if prompt_index == 0 else "re_explain_repo"), 0.6
    return None, 0.0


def _looks_like_path(token: str) -> bool:
    if token.startswith("-") or not token:
        return False
    return "/" in token or token.startswith(".") or "." in Path(token).name


def bash_context_paths(command: str) -> list[str]:
    """Paths a read-only command inspected. Conservative: only obvious path
    arguments, so the re-derivation metric is not polluted by flags/patterns."""
    import shlex

    try:
        parts = shlex.split(command)
    except ValueError:
        return []
    if not parts:
        return []
    head = Path(parts[0]).name
    args = [p for p in parts[1:] if not p.startswith("-")]

    if head in BASH_PATH_COMMANDS:
        if head == "ls" and not args:
            return []
        return args[:8]
    if head in BASH_SEARCH_COMMANDS:
        # first non-flag arg is the pattern; the rest are candidate paths
        return [p for p in args[1:] if _looks_like_path(p)][:8]
    if head == "git":
        paths: list[str] = []
        for i, part in enumerate(parts):
            if part == "-C" and i + 1 < len(parts):
                paths.append(parts[i + 1])
            if part == "--":
                paths.extend(parts[i + 1 :])
        return [p for p in paths if _looks_like_path(p)][:8]
    return []


def _iter_jsonl(path: Path):
    with path.open("r", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


@dataclass
class ToolRecorder:
    """Canonical tool-call accounting shared by every harness parser.

    Both parsers must produce identical metrics for identical behavior, or
    cross-harness comparisons are meaningless. Harness code only maps its tool
    names to canonical categories and hands over the arguments.
    """

    sig: Signals
    root: str | None = None
    cwd: str | None = None
    reads: set[str] = field(default_factory=set)
    edits: set[str] = field(default_factory=set)
    seen_paths: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, canonical: str, tool_input: dict, timestamp: str | None = None) -> None:
        if canonical == "bash":
            cmd = str(tool_input.get("command") or "")
            if BASH_READ_ONLY_RE.match(cmd):
                # Context gathering, not mutation: count as a read and inspect
                # path arguments, because real sessions explore via cat/rg/git
                # far more than via dedicated read tools.
                self.sig.tool_counts["read"] = self.sig.tool_counts.get("read", 0) + 1
                for raw_path in bash_context_paths(cmd):
                    self._path(raw_path, "reads")
            else:
                self.sig.tool_counts["bash"] = self.sig.tool_counts.get("bash", 0) + 1
            return

        self.sig.tool_counts[canonical] = self.sig.tool_counts.get(canonical, 0) + 1
        if canonical == "edit" and self.sig.first_edit_at is None and timestamp:
            self.sig.first_edit_at = timestamp
        raw = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
        key = CANONICAL_PATH_KEYS.get(canonical)
        if raw and key:
            self._path(str(raw), key)

    def _path(self, raw: str, key: str) -> None:
        # Fall back to the repo root when the session cwd is unknown: relative
        # bash paths are normally relative to the repo root anyway.
        normalized = _normalize(raw, self.root, self.cwd or self.root)
        counters = self.seen_paths.setdefault(normalized, {"reads": 0, "searches": 0, "edits": 0})
        counters[key] += 1
        if key == "reads":
            self.reads.add(normalized)
        elif key == "edits":
            self.edits.add(normalized)

    def finish(self) -> None:
        self.sig.files_read = len(self.reads)
        self.sig.files_edited = len(self.edits)
        self.sig.paths = self.seen_paths
        self.sig._ratio()


def add_usage(
    sig: Signals,
    input_tokens: int | None = 0,
    output_tokens: int | None = 0,
    cache_read: int | None = 0,
    cache_write: int | None = 0,
) -> None:
    """Cache reads/writes are input: they are tokens the provider processed."""
    sig.tokens_in += int(input_tokens or 0) + int(cache_read or 0) + int(cache_write or 0)
    sig.tokens_out += int(output_tokens or 0)


def analyze_transcript(
    transcript_path: str | Path, root: str | None = None, cwd: str | None = None
) -> Signals:
    """Parse a Claude Code JSONL transcript into aggregate signals."""
    sig = Signals()
    path = Path(transcript_path)
    if not path.exists():
        return sig
    if path.stat().st_size > MAX_TRANSCRIPT_BYTES:
        return sig  # too large for per-turn parsing; skip rather than stall the hook

    rec = ToolRecorder(sig, root, cwd)
    prompt_index = 0

    for entry in _iter_jsonl(path):
        etype = entry.get("type")
        if entry.get("isCompactSummary") or etype == "summary":
            sig.compaction_count += 1

        message = entry.get("message") or {}
        content = message.get("content")

        if etype == "user":
            if isinstance(content, str) and not content.lstrip().startswith("<"):
                cls, conf = detect_restatement(content, prompt_index)
                sig.prompts += 1
                if cls:
                    sig.restatement_count += 1
                    sig.restatement_classes[cls] = sig.restatement_classes.get(cls, 0) + 1
                    sig.restatement_confidence = max(sig.restatement_confidence, conf)
                prompt_index += 1
            continue

        if etype != "assistant" or entry.get("isSidechain"):
            continue

        usage = message.get("usage") or {}
        add_usage(
            sig,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cache_read=usage.get("cache_read_input_tokens"),
            cache_write=usage.get("cache_creation_input_tokens"),
        )

        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            canonical = TOOL_CATEGORY.get(block.get("name") or "")
            if canonical:
                rec.record(canonical, block.get("input") or {}, entry.get("timestamp"))

    rec.finish()
    return sig


def _normalize(raw: str, root: str | None, base: str | None = None) -> str:
    # Imported lazily to keep this module dependency-light for the hook path.
    from .repodetect import normalize_path

    return normalize_path(raw, root, base)
