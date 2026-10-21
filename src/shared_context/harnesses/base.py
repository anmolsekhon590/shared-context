"""Harness adapters: installation and transcript parsing per agent harness.

A harness adapter is the only place that knows one harness's conventions:
where its hooks/extensions live, what its transcript looks like, and which
tool names map to the canonical categories in `analyzer.ToolRecorder`.
Everything downstream — signals, HMAC path keys, spool, server, metrics —
is harness-neutral, so metrics stay comparable across harnesses.
"""

from __future__ import annotations

from pathlib import Path

from ..analyzer import Signals


class Harness:
    """Adapter interface. Implementations live next to this module."""

    name: str = "unknown"
    label: str = "Unknown"
    #: instruction file this harness reads natively
    doc_preference: str = "AGENTS.md"
    #: whether the harness supports context injection (Phase 1)
    supports_active: bool = False

    def install(self, mode: str) -> list[Path]:
        raise NotImplementedError

    def uninstall(self) -> list[Path]:
        raise NotImplementedError

    def is_installed(self) -> bool:
        return False

    def parse(
        self, transcript: str | Path | None, root: str | None = None, cwd: str | None = None
    ) -> Signals:
        if not transcript:
            return Signals()
        return self._parse(transcript, root, cwd)

    def _parse(self, transcript: str | Path, root: str | None, cwd: str | None) -> Signals:
        raise NotImplementedError
