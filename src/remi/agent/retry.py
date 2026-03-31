"""Retry policy for module execution.

LLM provider SDKs (Anthropic, OpenAI) handle transport-level retries
(rate limits, 5xx, timeouts) internally with proper backoff.  This
policy is for *application-level* recovery — e.g. retrying the whole
agent run when a transient infrastructure error causes the run to fail.

Only genuinely transient errors should be retried.  Config/auth errors
(bad API key, unknown model) must fail immediately.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import structlog

from remi.observability.events import Event
from remi.shared.errors import RetryExhaustedError

T = TypeVar("T")

logger = structlog.get_logger("remi.retry")


def _default_transient_exceptions() -> tuple[type[Exception], ...]:
    """Build the tuple of exception types considered transient.

    Imports SDK errors at call time so that missing optional
    dependencies don't break the module.
    """
    transient: list[type[Exception]] = [
        ConnectionError,
        TimeoutError,
        OSError,
    ]

    try:
        import anthropic
        transient.extend([
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
            anthropic.RateLimitError,
        ])
    except ImportError:
        pass

    try:
        import openai
        transient.extend([
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
            openai.RateLimitError,
        ])
    except ImportError:
        pass

    return tuple(transient)


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    delay_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=_default_transient_exceptions,
    )

    async def execute(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        last_exception: Exception | None = None
        delay = self.delay_seconds

        for attempt in range(1, self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except self.retryable_exceptions as exc:
                last_exception = exc
                logger.warning(
                    Event.RETRY_ATTEMPT,
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
            Event.RETRY_EXHAUSTED,
            max_retries=self.max_retries,
            error=str(last_exception),
            error_type=type(last_exception).__name__ if last_exception else None,
        )
        raise RetryExhaustedError(
            f"All {self.max_retries} retry attempts failed: {last_exception}",
            attempts=self.max_retries,
            last_error=last_exception,
        ) from last_exception
