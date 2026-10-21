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

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
PATH_SOURCES = {"Read": "reads", "Grep": "searches", "Glob": "searches", "Edit": "edits", "Write": "edits"}

MAX_TRANSCRIPT_BYTES = 20 * 1024 * 1024

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


def analyze_transcript(transcript_path: str | Path, root: str | None = None) -> Signals:
    """Parse a Claude Code JSONL transcript into aggregate signals."""
    sig = Signals()
    path = Path(transcript_path)
    if not path.exists():
        return sig
    if path.stat().st_size > MAX_TRANSCRIPT_BYTES:
        return sig  # too large for per-turn parsing; skip rather than stall the hook

    reads: set[str] = set()
    edits: set[str] = set()
    seen_paths: dict[str, dict[str, int]] = {}
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
        sig.tokens_in += int(
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
        )
        sig.tokens_out += int(usage.get("output_tokens") or 0)

        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            if name == "Bash":
                # Read-only commands are context gathering, not mutation: count
                # them as reads so the overhead ratio reflects intent.
                cmd = str((block.get("input") or {}).get("command") or "")
                key = "read" if re.match(
                    r"^\s*(ls|cat|head|tail|rg|grep|find|git (log|show|diff|status|branch)|wc|tree|file)\b",
                    cmd,
                ) else "bash"
                sig.tool_counts[key] = sig.tool_counts.get(key, 0) + 1
            else:
                category = TOOL_CATEGORY.get(name)
                if category:
                    sig.tool_counts[category] = sig.tool_counts.get(category, 0) + 1
            if name in EDIT_TOOLS and sig.first_edit_at is None:
                ts = entry.get("timestamp")
                if ts:
                    sig.first_edit_at = ts

            inp = block.get("input") or {}
            raw = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
            if not raw:
                continue
            normalized = _normalize(raw, root)
            counter_key = PATH_SOURCES.get(name)
            if not counter_key:
                continue
            counters = seen_paths.setdefault(normalized, {"reads": 0, "searches": 0, "edits": 0})
            counters[counter_key] += 1
            if counter_key == "reads":
                reads.add(normalized)
            elif counter_key == "edits":
                edits.add(normalized)

    sig.files_read = len(reads)
    sig.files_edited = len(edits)
    sig.paths = seen_paths
    sig._ratio()
    return sig


def _normalize(raw: str, root: str | None) -> str:
    # Imported lazily to keep this module dependency-light for the hook path.
    from .repodetect import normalize_path

    return normalize_path(raw, root)
