"""Client config and state paths.

Config is JSON at ``~/.config/shared-context/config.json``; mutable state
(spool, session map, cached path keys, pending signals) lives under
``~/.local/state/shared-context/``. Environment variables override both so the
recorder can run in CI or a sandbox without touching the user's home.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_SERVER_URL = "http://127.0.0.1:8787"
DEFAULT_TOKEN = "dev-token"


def config_dir() -> Path:
    return Path(os.environ.get("CTX_CONFIG_DIR", Path.home() / ".config" / "shared-context"))


def state_dir() -> Path:
    return Path(os.environ.get("CTX_STATE_DIR", Path.home() / ".local" / "state" / "shared-context"))


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class Config:
    server_url: str = DEFAULT_SERVER_URL
    token: str = DEFAULT_TOKEN
    mode: str = "observe"  # observe | active
    principal: str = ""  # hashed external identity, never an email in clear
    transcripts: str = "none"  # none | excerpt | full
    path_signals: bool = True
    restatement: bool = True
    hooks_installed: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> Config:
        cfg = cls()
        p = config_path()
        if p.exists():
            try:
                data = json.loads(p.read_text())
                for key in asdict(cfg):
                    if key in data:
                        setattr(cfg, key, data[key])
                cfg.extra = {k: v for k, v in data.items() if k not in asdict(cfg)}
            except (OSError, ValueError):
                pass
        cfg.server_url = os.environ.get("CTX_SERVER_URL", cfg.server_url)
        cfg.token = os.environ.get("CTX_TOKEN", cfg.token)
        cfg.mode = os.environ.get("CTX_MODE", cfg.mode)
        if os.environ.get("CTX_PRINCIPAL"):
            cfg.principal = os.environ["CTX_PRINCIPAL"]
        if not cfg.principal:
            cfg.principal = default_principal()
        return cfg

    def save(self) -> None:
        config_dir().mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload.update(self.extra)
        config_path().write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def default_principal() -> str:
    """A stable, non-reversible identity hint: hashed git email or OS user."""
    seed = ""
    try:
        seed = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        seed = ""
    seed = seed or os.environ.get("USER", "unknown")
    return "p_" + hashlib.sha256(seed.encode()).hexdigest()[:16]


def db_url() -> str:
    return os.environ.get("CTX_DB_URL", "postgresql://ctx:ctx@127.0.0.1:55432/ctx")


def path_key_secret() -> str:
    return os.environ.get("CTX_PATH_KEY_SECRET", "dev-path-key-secret")
