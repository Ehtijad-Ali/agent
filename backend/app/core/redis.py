"""Optional Redis connection, and the scan lock built on it.

Redis is what makes the lock hold across processes: with several API workers,
or the scheduler and a manual "Run scan" firing together, only one scan runs
at a time. Without REDIS_URL the lock still works inside this one process,
which is all a single-worker local setup needs.
"""

from __future__ import annotations

import logging
import threading
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger("signal.redis")

SCAN_LOCK_KEY = "signal:scan-lock"
# Longer than any real scan; a crashed holder must not block scans forever.
SCAN_LOCK_TTL_SECONDS = 30 * 60

_local_lock = threading.Lock()


@lru_cache
def get_redis():  # noqa: ANN201 -- redis.Redis | None, without importing redis eagerly
    url = get_settings().redis_url
    if not url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 -- Redis down degrades to the local lock
        logger.warning("Redis at REDIS_URL is unreachable (%s); using an in-process lock.", exc)
        return None


def redis_status() -> str:
    if not get_settings().redis_url:
        return "not_configured"
    client = get_redis()
    if client is None:
        return "unreachable"
    try:
        client.ping()
        return "ok"
    except Exception:  # noqa: BLE001
        return "unreachable"


@contextmanager
def scan_lock() -> Iterator[bool]:
    """Yields True when this caller holds the lock, False if a scan is running."""
    client = get_redis()
    if client is None:
        acquired = _local_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                _local_lock.release()
        return

    token = uuid.uuid4().hex
    acquired = bool(client.set(SCAN_LOCK_KEY, token, nx=True, ex=SCAN_LOCK_TTL_SECONDS))
    try:
        yield acquired
    finally:
        if acquired:
            # Release only our own lock, never one a later holder took after
            # ours expired.
            try:
                if client.get(SCAN_LOCK_KEY) == token.encode():
                    client.delete(SCAN_LOCK_KEY)
            except Exception:  # noqa: BLE001 -- the TTL cleans up regardless
                pass
