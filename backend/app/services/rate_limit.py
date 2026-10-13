"""Small per-user sliding-window rate limiter (plan §9).

In-process only: good enough for a single API instance. Use Redis or the
API gateway's limiter when running multiple replicas.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.config import get_settings
from app.errors import AppError

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def check(user_id: str, action: str, limit: int | None = None, window: float = 60.0) -> None:
    limit = limit or get_settings().rate_limit_per_minute
    key = f"{user_id}:{action}"
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            retry = int(window - (now - q[0])) + 1
            raise AppError(429, "rate_limited", "ทำรายการถี่เกินไป กรุณารอสักครู่แล้วลองใหม่", retry_after=retry)
        q.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
