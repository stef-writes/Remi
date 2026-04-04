"""Generic provenance-based conflict resolution — domain-agnostic.

When ingestion produces a fact that contradicts an existing one the
resolver compares ``FactProvenance`` on both sides and decides whether
to accept, reject, or record a conflict.

Rules (in priority order):
1. User-overridden facts are immutable unless another user overrides.
2. Higher confidence wins at the same recency.
3. More recent wins at the same confidence.
4. Conflicts are recorded as ``Annotation`` entities linked to the
   disputed entity so the agent can surface them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

import structlog

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.graph.types import (
    Annotation,
    FactProvenance,
    KnowledgeProvenance,
)

_log = structlog.get_logger(__name__)


class ConflictOutcome(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    CONFLICT = "conflict"


def resolve_conflict(
    existing: FactProvenance | None,
    incoming: FactProvenance,
) -> ConflictOutcome:
    """Decide whether *incoming* should overwrite *existing*."""
    if existing is None:
        return ConflictOutcome.ACCEPT

    if existing.overridden_by is not None and incoming.source != "user":
        return ConflictOutcome.REJECT

    if incoming.source == "user":
        return ConflictOutcome.ACCEPT

    if incoming.confidence > existing.confidence:
        return ConflictOutcome.ACCEPT
    if incoming.confidence < existing.confidence:
        return ConflictOutcome.REJECT

    incoming_ts = incoming.ingested_at or datetime.min.replace(tzinfo=UTC)
    existing_ts = existing.ingested_at or datetime.min.replace(tzinfo=UTC)
    if incoming_ts > existing_ts:
        return ConflictOutcome.ACCEPT

    return ConflictOutcome.CONFLICT


async def record_conflict(
    kg: KnowledgeGraph,
    *,
    entity_id: str,
    entity_type: str,
    field: str,
    existing_value: str,
    incoming_value: str,
    existing_provenance: FactProvenance,
    incoming_provenance: FactProvenance,
) -> Annotation:
    """Write a conflict annotation to the knowledge graph and return it."""
    annotation = Annotation(
        annotation_id=f"conflict:{uuid4().hex[:12]}",
        content=(
            f"Conflicting values for {entity_type}.{field}: "
            f"existing='{existing_value}' (source={existing_provenance.source}, "
            f"confidence={existing_provenance.confidence}) vs "
            f"incoming='{incoming_value}' (source={incoming_provenance.source}, "
            f"confidence={incoming_provenance.confidence})"
        ),
        annotation_type="conflict",
        target_entity_id=entity_id,
        target_entity_type=entity_type,
        provenance=FactProvenance(
            source="conflict_resolver",
            confidence=1.0,
            ingested_at=datetime.now(UTC),
            provenance_type=KnowledgeProvenance.DATA_DERIVED,
        ),
    )

    await kg.put_object(
        "Annotation",
        annotation.annotation_id,
        annotation.model_dump(mode="json"),
    )
    await kg.put_link(
        entity_id,
        "HAS_ANNOTATION",
        annotation.annotation_id,
        properties={"annotation_type": "conflict"},
    )

    _log.info(
        "conflict_recorded",
        entity_id=entity_id,
        entity_type=entity_type,
        field=field,
        existing_source=existing_provenance.source,
        incoming_source=incoming_provenance.source,
    )
    return annotation
