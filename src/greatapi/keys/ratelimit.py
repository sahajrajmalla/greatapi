"""Rate limiting.

The default limiter keeps a sliding window in memory. That is exact for a
single process and approximate across several, so a multi-process deployment
that needs a hard global ceiling should supply a shared implementation of
:class:`RateLimiter` via :func:`set_rate_limiter`.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Protocol

__all__ = ["InMemoryRateLimiter", "RateLimiter", "get_rate_limiter", "set_rate_limiter"]


class RateLimiter(Protocol):
    """Fixed-cost sliding-window limiter."""

    async def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        """Record a request.

        Returns ``None`` when the request is allowed, or the number of seconds
        to wait before retrying when it is not.
        """
        ...


class InMemoryRateLimiter:
    """Per-process sliding window."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, key: str, limit: int, window_seconds: float) -> float | None:
        now = time.monotonic()
        window = self._hits[key]
        cutoff = now - window_seconds
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= limit:
            return max(0.0, window[0] + window_seconds - now)

        window.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()


_limiter: RateLimiter = InMemoryRateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Install a custom limiter, e.g. one backed by Redis."""
    global _limiter
    _limiter = limiter
