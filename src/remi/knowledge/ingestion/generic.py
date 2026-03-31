"""Generic (non-AppFolio) document ingestion via column classification heuristics."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from remi.knowledge.ingestion.helpers import entity_id_from_row
from remi.models.memory import KnowledgeStore, Relationship

if TYPE_CHECKING:
    from remi.knowledge.ingestion.base import IngestionResult
    from remi.models.documents import Document

_COLUMN_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("property", re.compile(r"property|building|address|location|complex", re.I)),
    ("tenant", re.compile(r"tenant|resident|occupant|renter|lessee", re.I)),
    ("unit", re.compile(r"unit|apt|suite|apartment|room|space", re.I)),
    ("lease", re.compile(r"lease|contract|agreement|term", re.I)),
    (
        "maintenance",
        re.compile(r"maintenance|repair|work.?order|service.?request|issue|ticket", re.I),
    ),
    (
        "financial",
        re.compile(r"rent|revenue|income|expense|cost|amount|payment|fee|price|noi", re.I),
    ),
]

_RELATIONSHIP_RULES: list[tuple[str, str, str]] = [
    ("tenant", "unit", "occupies"),
    ("unit", "property", "belongs_to"),
    ("lease", "unit", "covers"),
    ("lease", "tenant", "signed_by"),
    ("maintenance", "unit", "affects"),
    ("maintenance", "property", "reported_at"),
    ("financial", "property", "recorded_for"),
    ("financial", "unit", "recorded_for"),
    ("financial", "tenant", "charged_to"),
]


def classify_columns(column_names: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for col in column_names:
        for entity_type, pattern in _COLUMN_RULES:
            if pattern.search(col):
                mapping[col] = entity_type
                break
    return mapping


async def ingest_generic(
    doc: Document,
    namespace: str,
    result: IngestionResult,
    kb: KnowledgeStore,
    upsert_entity: Any,
) -> None:
    import structlog

    logger = structlog.get_logger(__name__)

    col_map = classify_columns(doc.column_names)
    if not col_map:
        result.ambiguous_rows = list(doc.rows)
        logger.info(
            "no_columns_matched",
            doc_id=doc.id,
            columns=doc.column_names,
            ambiguous=len(doc.rows),
        )
        return

    for row_idx, row in enumerate(doc.rows):
        row_entities = await _extract_row(
            row, row_idx, col_map, namespace, doc.id, result, kb, upsert_entity
        )
        if not row_entities:
            result.ambiguous_rows.append(row)
        result.relationships_created += await _infer_relationships(row_entities, namespace, kb)


async def _extract_row(
    row: dict[str, Any],
    row_idx: int,
    col_map: dict[str, str],
    namespace: str,
    doc_id: str,
    result: IngestionResult,
    kb: KnowledgeStore,
    upsert_entity: Any,
) -> dict[str, str]:
    type_to_props: dict[str, dict[str, Any]] = {}
    for col, val in row.items():
        entity_type = col_map.get(col)
        if entity_type is None or val is None:
            continue
        type_to_props.setdefault(entity_type, {})[col] = val

    row_entities: dict[str, str] = {}
    for entity_type, props in type_to_props.items():
        eid = entity_id_from_row(entity_type, row, row_idx, doc_id)
        await upsert_entity(eid, entity_type, namespace, props, result)
        row_entities[entity_type] = eid

    return row_entities


async def _infer_relationships(
    row_entities: dict[str, str],
    namespace: str,
    kb: KnowledgeStore,
) -> int:
    count = 0
    for source_type, target_type, relation in _RELATIONSHIP_RULES:
        source_id = row_entities.get(source_type)
        target_id = row_entities.get(target_type)
        if source_id and target_id and source_id != target_id:
            await kb.put_relationship(
                Relationship(
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation,
                    namespace=namespace,
                )
            )
            count += 1
    return count
