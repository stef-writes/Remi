"""Document models and store port."""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Document(BaseModel):
    """A parsed document with extracted tabular data."""

    id: str
    filename: str
    content_type: str  # text/csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, etc.
    uploaded_at: datetime = Field(default_factory=_utcnow)
    row_count: int = 0
    column_names: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentStore(abc.ABC):

    @abc.abstractmethod
    async def save(self, document: Document) -> None: ...

    @abc.abstractmethod
    async def get(self, document_id: str) -> Document | None: ...

    @abc.abstractmethod
    async def list_documents(self) -> list[Document]: ...

    @abc.abstractmethod
    async def delete(self, document_id: str) -> bool: ...

    @abc.abstractmethod
    async def query_rows(
        self,
        document_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...
