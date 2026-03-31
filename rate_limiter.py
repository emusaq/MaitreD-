"""Sliding-window rate limiter (per key, e.g. phone number).

Uses Redis sorted sets when REDIS_URL is configured.
Falls back to in-memory deque when Redis is not available (single-process dev only).
"""
import hashlib
import time as _time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional

import redis as _redis_lib
from utils import logger
from config import RATE_LIMIT_COUNT, RATE_LIMIT_WINDOW, REDIS_URL as _REDIS_URL
_redis_client: Optional[_redis_lib.Redis] = None

if _REDIS_URL:
    try:
        _redis_client = _redis_lib.Redis.from_url(_REDIS_URL, decode_responses=True)
        _redis_client.ping()
    except Exception as _e:
        logger.error(f"Redis connection failed ({_e}); rate limiter falling back to in-memory.")
        _redis_client = None
else:
    logger.warning(
        "REDIS_URL not set — rate limiter using in-memory fallback. "
        "Not suitable for multi-process deployments."
    )

# In-memory fallback state
_windows: dict = defaultdict(deque)


def _set_redis_client(client: Optional[_redis_lib.Redis]) -> None:
    """Inject a Redis client (used by tests to swap in fakeredis)."""
    global _redis_client
    _redis_client = client


def is_allowed(key: str, limit: int = RATE_LIMIT_COUNT, window_seconds: int = RATE_LIMIT_WINDOW) -> bool:
    """Return True if the key is within the rate limit, False if exceeded."""
    if _redis_client is not None:
        return _redis_is_allowed(key, limit, window_seconds)
    return _memory_is_allowed(key, limit, window_seconds)


def _redis_is_allowed(key: str, limit: int, window_seconds: int) -> bool:
    hashed = hashlib.sha256(key.encode()).hexdigest()[:16]
    redis_key = f"rate:{hashed}"
    now = _time.time()
    cutoff = now - window_seconds

    try:
        pipe = _redis_client.pipeline()
        pipe.zremrangebyscore(redis_key, "-inf", cutoff)
        pipe.zcard(redis_key)
        count_results = pipe.execute()
        count = count_results[1]

        if count >= limit:
            return False

        pipe2 = _redis_client.pipeline()
        pipe2.zadd(redis_key, {str(uuid.uuid4()): now})
        pipe2.expire(redis_key, window_seconds)
        pipe2.execute()
        return True
    except Exception as e:
        logger.error(f"Redis rate limiter error ({e}); allowing request.")
        return True  # Fail open: don't block users if Redis is down


def _memory_is_allowed(key: str, limit: int, window_seconds: int) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    q = _windows[key]

    while q and q[0] < cutoff:
        q.popleft()

    if not q and key in _windows:
        del _windows[key]
        q = _windows[key]

    if len(q) >= limit:
        return False

    q.append(now)
    return True
