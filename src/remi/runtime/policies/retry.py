"""Retry policy for module execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)

    async def execute(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        last_exception: Exception | None = None
        delay = self.delay_seconds

        for attempt in range(1, self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except self.retryable_exceptions as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    delay *= self.backoff_multiplier

        raise last_exception  # type: ignore[misc]
