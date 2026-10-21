"""Harness registry. `ctx init --harness <name|all>` selects from here."""

from __future__ import annotations

from .base import Harness
from .claude_code import ClaudeCodeHarness
from .pi import PiHarness

HARNESSES: dict[str, Harness] = {
    "claude-code": ClaudeCodeHarness(),
    "pi": PiHarness(),
}


def names() -> list[str]:
    return list(HARNESSES)


def get(name: str | None) -> Harness:
    return HARNESSES.get(str(name or ""), HARNESSES["claude-code"])


def select(spec: str) -> list[Harness]:
    if spec == "all":
        return list(HARNESSES.values())
    return [get(spec)]
