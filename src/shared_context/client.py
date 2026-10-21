"""HTTP client. Every call fails open: on any network error the payload is
spooled locally and the hook returns immediately."""

from __future__ import annotations

import time
from typing import Any

import httpx

from . import spool
from .config import Config

TIMEOUT = httpx.Timeout(2.0, connect=0.5)


class Client:
    def __init__(self, config: Config, timeout: float = 2.0):
        self.config = config
        self.timeout = httpx.Timeout(timeout, connect=min(0.5, timeout))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.token}"}

    def post(self, path: str, payload: dict, key: str | None = None, spool_on_fail: bool = True) -> dict | None:
        try:
            with httpx.Client(timeout=self.timeout) as http:
                resp = http.post(
                    self.config.server_url + path,
                    json=payload,
                    headers={**self._headers(), **({"Idempotency-Key": key} if key else {})},
                )
                if resp.status_code < 300:
                    return resp.json() if resp.content else {}
                if resp.status_code >= 500 and spool_on_fail:
                    spool.append("POST", path, payload, key)
                return None
        except httpx.HTTPError:
            if spool_on_fail:
                spool.append("POST", path, payload, key)
            return None

    def get(self, path: str, params: dict | None = None) -> dict | None:
        try:
            with httpx.Client(timeout=self.timeout) as http:
                resp = http.get(
                    self.config.server_url + path, params=params, headers=self._headers()
                )
                if resp.status_code < 300:
                    return resp.json() if resp.content else {}
        except httpx.HTTPError:
            return None
        return None

    def flush(self, limit: int = 200) -> tuple[int, int]:
        """Send queued payloads. Returns (sent, remaining)."""
        entries = spool.read_all()
        if not entries:
            return 0, 0
        sent = 0
        remaining: list[dict] = []
        for entry in entries[:limit]:
            result = self.post(
                entry["path"], entry["payload"], entry.get("key"), spool_on_fail=False
            )
            if result is None:
                remaining.append(entry)
            else:
                sent += 1
        remaining.extend(entries[limit:])
        spool.rewrite(remaining)
        return sent, len(remaining)


def health(config: Config) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=httpx.Timeout(1.5, connect=0.5)) as http:
            resp = http.get(config.server_url + "/healthz")
            if resp.status_code < 300:
                return resp.json()
    except httpx.HTTPError:
        return None
    return None


def retry_loop(config: Config, seconds: float = 0.0) -> None:
    deadline = time.time() + seconds
    client = Client(config)
    while True:
        sent, remaining = client.flush()
        if remaining == 0 or time.time() >= deadline:
            break
        time.sleep(min(1.0, max(0.0, deadline - time.time())))
