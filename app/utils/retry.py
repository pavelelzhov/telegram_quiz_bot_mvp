from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar('T')


async def retry_async(
    action: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    base_delay_sec: float = 0.6,
    should_retry: Callable[[Exception], bool] | None = None,
) -> T:
    attempt = 0
    while True:
        try:
            return await action()
        except Exception as exc:
            if attempt >= retries:
                raise
            if should_retry and not should_retry(exc):
                raise
            await asyncio.sleep(base_delay_sec * (2 ** attempt))
            attempt += 1
