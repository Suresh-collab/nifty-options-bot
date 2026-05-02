"""
Phase 5.4 — Alert de-duplication.

Same alert key within TTL seconds → only first delivery fires;
subsequent calls are silently dropped.

Thread-safe for async use: the dict is read/written under the event loop's
single-threaded execution model (no explicit lock needed in async code).
"""
from __future__ import annotations

import time
from typing import Optional


class AlertDedup:
    """
    In-memory dedup store.  Tracks last-sent timestamp per alert key.
    TTL defaults to 60 seconds (Phase 5.4 requirement).
    """

    def __init__(self, ttl_seconds: float = 60.0):
        self._ttl = ttl_seconds
        self._last_sent: dict[str, float] = {}

    def should_send(self, key: str) -> bool:
        """
        Return True if the alert should be delivered (not a duplicate).
        Records the send time so the next call within TTL returns False.
        """
        now = time.monotonic()
        last = self._last_sent.get(key)
        if last is None or (now - last) >= self._ttl:
            self._last_sent[key] = now
            return True
        return False

    def reset(self, key: Optional[str] = None) -> None:
        """Clear one key or the whole store (useful in tests)."""
        if key is None:
            self._last_sent.clear()
        else:
            self._last_sent.pop(key, None)

    def time_until_next(self, key: str) -> float:
        """Seconds remaining until the key cools down (0 if already cooled)."""
        last = self._last_sent.get(key)
        if last is None:
            return 0.0
        remaining = self._ttl - (time.monotonic() - last)
        return max(0.0, remaining)


# Module-level singleton used by telegram and email senders.
_dedup = AlertDedup(ttl_seconds=60.0)


def should_send(key: str) -> bool:
    return _dedup.should_send(key)


def reset(key: Optional[str] = None) -> None:
    _dedup.reset(key)
