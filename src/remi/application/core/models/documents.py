"""Documents — uploaded files scoped to domain entities.

A Document is the identity and provenance layer for an uploaded file.
Content (chunks, rows, raw text) lives in the agent-layer ContentStore.

Every field here answers one of three questions:
  - WHAT is it?   (filename, content_type, document_type, kind, size)
  - WHAT DOES IT COVER?  (report_type, platform, scope, effective_date, coverage)
  - WHO / WHERE?  (manager_id, property_id, unit_id, lease_id)
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from remi.application.core.models._helpers import _utcnow
from remi.application.core.models.date_range import DateRange
from remi.application.core.models.enums import (
    DocumentType,
    ImportStatus,
    Platform,
    ReportScope,
    ReportType,
)


class Document(BaseModel, frozen=True):
    id: str
    filename: str
    content_type: str
    content_hash: str = ""
    document_type: DocumentType = DocumentType.OTHER
    uploaded_at: datetime = Field(default_factory=_utcnow)

    # --- Entity scope FKs (auto-materialized as graph edges) -----------------
    unit_id: str | None = None
    property_id: str | None = None
    lease_id: str | None = None
    manager_id: str | None = None

    # --- Content shape -------------------------------------------------------
    kind: str = "text"
    page_count: int = 0
    chunk_count: int = 0
    row_count: int = 0
    size_bytes: int = 0
    tags: list[str] = Field(default_factory=list)

    # --- Report provenance ---------------------------------------------------
    report_type: ReportType = ReportType.UNKNOWN
    platform: Platform = Platform.UNKNOWN
    scope: ReportScope = ReportScope.UNKNOWN
    import_status: ImportStatus = ImportStatus.COMPLETE

    # The manager name extracted from the report title/metadata by the LLM.
    # Purely informational — NOT used for property assignment.
    # e.g. "Alex Budavich" from "Alex - Delinquency Report"
    report_manager: str | None = None

    # When the report was exported / run by the PM software.
    effective_date: date | None = None

    # The closed date interval the report DATA covers — separate from
    # effective_date.  A "2024 Annual History" exported 2025-01-15 has
    # effective_date=2025-01-15, coverage=[2024-01-01, 2024-12-31].
    # None for point-in-time snapshots that carry no explicit range.
    coverage: DateRange | None = None

    # FK to the report this one supersedes (e.g. a re-export of the same period).
    source_document_id: str | None = None
