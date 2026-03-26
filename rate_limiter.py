"""In-memory sliding-window rate limiter (per key, e.g. phone number).

Suitable for single-process beta deployments. For multi-process production,
replace _windows with a Redis backend.
"""
from collections import defaultdict, deque
from datetime import datetime, timedelta
from decouple import config

_windows: dict[str, deque] = defaultdict(deque)

RATE_LIMIT_COUNT = int(config("RATE_LIMIT_COUNT", default=10))
RATE_LIMIT_WINDOW = int(config("RATE_LIMIT_WINDOW", default=60))


def is_allowed(key: str, limit: int = RATE_LIMIT_COUNT, window_seconds: int = RATE_LIMIT_WINDOW) -> bool:
    """
    Return True if the key is within the rate limit, False if exceeded.
    Evicts expired entries before checking.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    q = _windows[key]

    # Drop timestamps outside the window
    while q and q[0] < cutoff:
        q.popleft()

    # Free the key entirely once the window is empty — prevents unbounded dict growth
    if not q and key in _windows:
        del _windows[key]
        q = _windows[key]  # defaultdict recreates it fresh

    if len(q) >= limit:
        return False

    q.append(now)
    return True
