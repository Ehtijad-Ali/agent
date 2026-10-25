"""Start long-running coroutines from anywhere, including sync routes.

FastAPI runs ``def`` endpoints in a worker thread, where there is no event
loop, so ``asyncio.create_task`` raises there. The server's loop is captured at
startup and work started from a thread is handed to it instead. Either way the
caller gets an object with ``done()`` and ``cancel()``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any

_loop: asyncio.AbstractEventLoop | None = None


def capture_loop() -> None:
    """Call once from startup, on the server's event loop."""
    global _loop
    _loop = asyncio.get_running_loop()


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task | Future:
    try:
        return asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        if _loop is None:
            coro.close()
            raise RuntimeError("Background loop not captured; call capture_loop() at startup.") from None
        return asyncio.run_coroutine_threadsafe(coro, _loop)
