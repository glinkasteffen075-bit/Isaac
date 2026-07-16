"""Run async coroutines from sync Isaac paths without nested-loop crashes."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, Coroutine, TypeVar

log = logging.getLogger("Isaac.ExternalMemory")

T = TypeVar("T")


def run_coro(coro: Coroutine[Any, Any, T], *, timeout: float | None = None) -> T:
    """Execute *coro* safely from sync code.

    - No running loop → asyncio.run
    - Running loop → dedicated thread with its own loop (avoid nested run)
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if timeout is None:
            return asyncio.run(coro)

        async def _with_timeout() -> T:
            return await asyncio.wait_for(coro, timeout=timeout)

        return asyncio.run(_with_timeout())

    def _runner() -> T:
        return asyncio.run(
            asyncio.wait_for(coro, timeout=timeout) if timeout is not None else coro
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_runner)
        return fut.result(timeout=(timeout + 1.0) if timeout else None)
