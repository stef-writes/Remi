"""Document content models and store port.

``DocumentContent`` holds the parsed payload (chunks, rows, raw text).
``ContentStore`` persists and queries that content.

The domain-level identity and relationships for a document live in
``application.core.models.documents.Document``.
"""

from __future__ import annotations

import abc
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DocumentKind(StrEnum):
    """Discriminator for how a document's content is structured."""

    tabular = "tabular"
    text = "text"
    image = "image"


class TextChunk(BaseModel):
    """A passage extracted from a text document."""

    index: int
    text: str
    page: int | None = None


class DocumentContent(BaseModel):
    """Parsed document content — tabular (CSV/Excel), text (PDF/DOCX/TXT), or image."""

    id: str
    filename: str
    content_type: str
    uploaded_at: datetime = Field(default_factory=_utcnow)
    effective_date: date | None = None

    kind: DocumentKind = DocumentKind.tabular

    row_count: int = 0
    column_names: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)

    chunks: list[TextChunk] = Field(default_factory=list)
    raw_text: str = ""
    page_count: int = 0

    tags: list[str] = Field(default_factory=list)
    size_bytes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentStore(abc.ABC):
    """Persists and queries parsed document content (chunks, rows, raw text)."""

    @abc.abstractmethod
    async def save(self, document: DocumentContent) -> None: ...

    @abc.abstractmethod
    async def get(self, document_id: str) -> DocumentContent | None: ...

    @abc.abstractmethod
    async def list_documents(self) -> list[DocumentContent]: ...

    @abc.abstractmethod
    async def delete(self, document_id: str) -> bool: ...

    @abc.abstractmethod
    async def query_rows(
        self,
        document_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    async def search_documents(
        self,
        *,
        query: str | None = None,
        kind: DocumentKind | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[DocumentContent]: ...

    @abc.abstractmethod
    async def update_tags(self, document_id: str, tags: list[str]) -> bool: ...
