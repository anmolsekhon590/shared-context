"""Repo identity detection and privacy-preserving path signals."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SSH = re.compile(r"^git@([^:]+):(.+?)(?:\.git)?$")
_HTTPS = re.compile(r"^https?://([^/]+)/(.+?)(?:\.git)?$")


@dataclass
class RepoRef:
    forge: str  # github | gitlab | local
    full_name: str  # owner/name, or local/<hash> when there is no remote
    root: str | None  # working directory
    branch: str | None


def _git(cwd: str, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=3
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def detect_repo(cwd: str | None = None) -> RepoRef:
    cwd = cwd or os.getcwd()
    top = _git(cwd, "rev-parse", "--show-toplevel")
    branch = None
    if top:
        branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    root = top or cwd

    url = _git(cwd, "remote", "get-url", "origin") if top else None
    if url:
        m = _SSH.match(url) or _HTTPS.match(url)
        if m:
            host, path = m.group(1), m.group(2).strip("/")
            forge = "gitlab" if "gitlab" in host else "github"
            return RepoRef(forge=forge, full_name=path, root=root, branch=branch)

    digest = hashlib.sha256(root.encode()).hexdigest()[:12]
    return RepoRef(forge="local", full_name=f"local/{digest}", root=root, branch=branch)


def repo_key(ref: RepoRef) -> str:
    return f"{ref.forge}:{ref.full_name}"


def normalize_path(path: str, root: str | None, base: str | None = None) -> str:
    """Relative to the repo root when possible; absolute otherwise.

    Relative inputs resolve against `base` (the session's working directory),
    never against the recorder's own cwd — otherwise `src/a.py` from a shell
    command would become a machine-specific signal and never match a teammate's.
    """
    if not path:
        return path
    try:
        p = Path(path).expanduser()
        if not p.is_absolute() and base:
            p = Path(base) / p
        abs_path = str(p.resolve())
    except OSError:
        return path
    if root:
        try:
            rel = os.path.relpath(abs_path, str(Path(root).resolve()))
            if not rel.startswith(".."):
                return rel
        except ValueError:
            pass
    return abs_path


def hash_path(key: bytes, normalized: str) -> bytes:
    """HMAC of a normalized path. The raw path never leaves the machine."""
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).digest()


def cwd_hash(root: str) -> bytes:
    return hashlib.sha256(root.encode("utf-8")).digest()
