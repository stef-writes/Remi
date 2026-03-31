"""TraceStore port — storage and retrieval of reasoning traces."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.domain.trace.types import Span, Trace


class TraceStore(abc.ABC):
    """Read/write access to trace spans."""

    @abc.abstractmethod
    async def put_span(self, span: Span) -> None: ...

    @abc.abstractmethod
    async def get_span(self, span_id: str) -> Span | None: ...

    @abc.abstractmethod
    async def list_spans(self, trace_id: str) -> list[Span]: ...

    @abc.abstractmethod
    async def list_traces(
        self,
        *,
        limit: int = 50,
        kind: str | None = None,
    ) -> list[Trace]: ...

    @abc.abstractmethod
    async def get_trace(self, trace_id: str) -> Trace | None: ...
