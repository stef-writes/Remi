"""Shared types for the ingestion pipeline.

Kept in a leaf module so ingestion submodules can import IngestionResult
without pulling in IngestionService and creating a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReviewKind(StrEnum):
    """Discriminator for human-reviewable items produced during ingestion."""

    AMBIGUOUS_ROW = "ambiguous_row"
    VALIDATION_WARNING = "validation_warning"
    ENTITY_MATCH = "entity_match"
    CLASSIFICATION_UNCERTAIN = "classification_uncertain"
    MANAGER_INFERRED = "manager_inferred"


class ReviewSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ACTION_NEEDED = "action_needed"


@dataclass
class ReviewOption:
    """One selectable choice for an entity-resolution review item."""

    id: str
    label: str


@dataclass
class ReviewItem:
    """A structured item surfaced to the human for post-upload review.

    Each item carries enough context to render an inline action in the UI
    and enough identifiers to submit a correction back to the API.
    """

    kind: ReviewKind
    severity: ReviewSeverity
    message: str
    row_index: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    field_name: str | None = None
    raw_value: str | None = None
    suggestion: str | None = None
    options: list[ReviewOption] = field(default_factory=list)
    row_data: dict[str, Any] | None = None


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
    review_items: list[ReviewItem] = field(default_factory=list)
