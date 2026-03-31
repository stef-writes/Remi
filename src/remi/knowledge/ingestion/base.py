"""Shared types for the ingestion pipeline.

Kept in a leaf module so the individual ingestors (delinquency, rent_roll,
lease_expiration, generic) can import IngestionResult without pulling in
IngestionService and creating a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IngestionResult:
    """Result of ingesting a document into the knowledge graph."""

    document_id: str
    report_type: str = "unknown"
    entities_created: int = 0
    relationships_created: int = 0
    ambiguous_rows: list[dict[str, Any]] = field(default_factory=list)
