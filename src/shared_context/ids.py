"""Client-generated, time-sortable UUIDv7 identifiers."""

from __future__ import annotations

import secrets
import time
import uuid


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7.

    Capture must work offline, so the client generates IDs. Time-sortable IDs
    keep index locality and make events orderable without a clock comparison.
    """
    ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    return uuid.UUID(int=value)


def uuid7_str() -> str:
    return str(uuid7())
