"""Documents — uploaded files scoped to domain entities.

A Document is the identity and relationship layer for an uploaded file.
Content (chunks, rows, raw text) lives in the agent-layer ContentStore.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from remi.application.core.models._helpers import _utcnow
from remi.application.core.models.enums import DocumentType


class Document(BaseModel, frozen=True):
    id: str
    filename: str
    content_type: str
    document_type: DocumentType = DocumentType.OTHER
    uploaded_at: datetime = Field(default_factory=_utcnow)
    effective_date: date | None = None

    unit_id: str | None = None
    property_id: str | None = None
    lease_id: str | None = None
    manager_id: str | None = None

    kind: str = "text"
    page_count: int = 0
    chunk_count: int = 0
    row_count: int = 0
    size_bytes: int = 0

    tags: list[str] = Field(default_factory=list)
    report_type: str = "unknown"
    source_document_id: str | None = None
