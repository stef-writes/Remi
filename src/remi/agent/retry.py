"""Retry policy for module execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")

logger = structlog.get_logger("remi.retry")


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
                logger.warning(
                    "retry_attempt",
                    attempt=attempt,
                    max_retries=self.max_retries,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    next_delay=delay if attempt < self.max_retries else None,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    delay *= self.backoff_multiplier

        logger.error(
            "retry_exhausted",
            max_retries=self.max_retries,
            error=str(last_exception),
            error_type=type(last_exception).__name__ if last_exception else None,
        )
        raise last_exception  # type: ignore[misc]
