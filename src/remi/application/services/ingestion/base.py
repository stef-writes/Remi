"""Shared types for the ingestion pipeline.

Kept in a leaf module so ingestion submodules can import IngestionResult
without pulling in IngestionService and creating a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RowWarning:
    """A single validation or persistence warning for an extracted row."""

    row_index: int
    row_type: str
    field: str
    issue: str
    raw_value: str


@dataclass
class IngestionResult:
    """Result of ingesting a document into the knowledge graph."""

    document_id: str
    report_type: str = "unknown"
    entities_created: int = 0
    relationships_created: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_skipped: int = 0
    validation_warnings: list[RowWarning] = field(default_factory=list)
    persist_errors: list[RowWarning] = field(default_factory=list)
    ambiguous_rows: list[dict[str, Any]] = field(default_factory=list)
    manager_tags_skipped: list[str] = field(default_factory=list)
