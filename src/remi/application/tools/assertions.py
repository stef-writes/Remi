"""User assertion tools — assert, correct, and contextualize facts in the KG.

These tools let the director (or the agent on their behalf) teach the system:
- **assert_fact**: add a new piece of knowledge
- **correct_entity**: fix a wrong value on an existing entity
- **add_context**: attach an annotation (user context) to an entity

All writes go through the same ``KnowledgeGraph`` path as ingestion but
with ``source="user"`` and ``confidence=1.0``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import structlog

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.graph.types import (
    FactProvenance,
    KnowledgeProvenance,
)
from remi.agent.llm.types import ToolArg, ToolDefinition
from remi.agent.types import ToolRegistry

_log = structlog.get_logger(__name__)

_USER_PROVENANCE = FactProvenance(
    source="user",
    confidence=1.0,
    provenance_type=KnowledgeProvenance.USER_STATED,
)


async def _assert_fact(
    kg: KnowledgeGraph,
    *,
    entity_type: str,
    entity_id: str | None = None,
    properties: dict[str, str],
    related_to: str | None = None,
    relation_type: str | None = None,
) -> dict[str, str]:
    """Assert a new fact into the knowledge graph with user provenance."""
    eid = entity_id or f"{entity_type.lower()}:{uuid4().hex[:12]}"

    props = {**properties, "asserted_by": "user", "asserted_at": datetime.now(UTC).isoformat()}
    await kg.put_object(entity_type, eid, props)

    if related_to and relation_type:
        await kg.put_link(
            eid, relation_type, related_to,
            properties={"provenance_source": "user"},
        )

    _log.info("user_fact_asserted", entity_type=entity_type, entity_id=eid)
    return {"status": "asserted", "entity_id": eid, "entity_type": entity_type}


async def _correct_entity(
    kg: KnowledgeGraph,
    *,
    entity_type: str,
    entity_id: str,
    corrections: dict[str, str],
) -> dict[str, str]:
    """Correct field values on an existing entity."""
    existing = await kg.get_object(entity_type, entity_id)
    if existing is None:
        return {"status": "not_found", "entity_id": entity_id}

    updated_props = {
        **existing.properties,
        **corrections,
        "corrected_by": "user",
        "corrected_at": datetime.now(UTC).isoformat(),
        "overridden_by": "user",
    }
    await kg.put_object(entity_type, entity_id, updated_props)

    _log.info(
        "user_correction_applied",
        entity_type=entity_type,
        entity_id=entity_id,
        fields=list(corrections.keys()),
    )
    return {"status": "corrected", "entity_id": entity_id, "fields": str(list(corrections.keys()))}


async def _add_context(
    kg: KnowledgeGraph,
    *,
    entity_type: str,
    entity_id: str,
    context: str,
) -> dict[str, str]:
    """Attach a user-context annotation to an entity."""
    aid = f"annotation:{uuid4().hex[:12]}"

    await kg.put_object("Annotation", aid, {
        "annotation_id": aid,
        "content": context,
        "annotation_type": "user_context",
        "target_entity_id": entity_id,
        "target_entity_type": entity_type,
        "source": "user",
        "confidence": "1.0",
        "extracted_at": datetime.now(UTC).isoformat(),
    })
    await kg.put_link(
        entity_id, "HAS_ANNOTATION", aid,
        properties={"annotation_type": "user_context"},
    )

    _log.info(
        "user_context_added",
        entity_type=entity_type,
        entity_id=entity_id,
        annotation_id=aid,
    )
    return {"status": "context_added", "annotation_id": aid, "entity_id": entity_id}


def register_assertion_tools(
    registry: ToolRegistry,
    *,
    knowledge_graph: KnowledgeGraph,
) -> None:
    """Register user-assertion tools on the agent tool registry."""

    async def assert_fact(
        entity_type: str,
        properties: dict[str, str],
        entity_id: str | None = None,
        related_to: str | None = None,
        relation_type: str | None = None,
    ) -> dict[str, str]:
        """Assert a new fact into the knowledge graph."""
        return await _assert_fact(
            knowledge_graph,
            entity_type=entity_type,
            entity_id=entity_id,
            properties=properties,
            related_to=related_to,
            relation_type=relation_type,
        )

    async def correct_entity(
        entity_type: str,
        entity_id: str,
        corrections: dict[str, str],
    ) -> dict[str, str]:
        """Correct field values on an existing entity in the knowledge graph."""
        return await _correct_entity(
            knowledge_graph,
            entity_type=entity_type,
            entity_id=entity_id,
            corrections=corrections,
        )

    async def add_context(
        entity_type: str,
        entity_id: str,
        context: str,
    ) -> dict[str, str]:
        """Attach user context/annotation to an entity in the knowledge graph."""
        return await _add_context(
            knowledge_graph,
            entity_type=entity_type,
            entity_id=entity_id,
            context=context,
        )

    registry.register(
        "assert_fact",
        assert_fact,
        ToolDefinition(
            name="assert_fact",
            description=(
                "Assert a new fact into the knowledge graph. Creates an entity with "
                "user-level provenance (highest confidence). Optionally link it to "
                "an existing entity."
            ),
            args=[
                ToolArg(name="entity_type", description="Entity type name", required=True),
                ToolArg(
                    name="properties", description="Entity properties as JSON",
                    type="object", required=True,
                ),
                ToolArg(name="entity_id", description="Optional entity ID"),
                ToolArg(name="related_to", description="ID of entity to link to"),
                ToolArg(name="relation_type", description="Link type for relation"),
            ],
        ),
    )
    registry.register(
        "correct_entity",
        correct_entity,
        ToolDefinition(
            name="correct_entity",
            description=(
                "Correct field values on an existing entity. User corrections have "
                "highest confidence and won't be overwritten by automated imports."
            ),
            args=[
                ToolArg(name="entity_type", description="Entity type name", required=True),
                ToolArg(name="entity_id", description="Entity ID to correct", required=True),
                ToolArg(
                    name="corrections", description="Field corrections as JSON",
                    type="object", required=True,
                ),
            ],
        ),
    )
    registry.register(
        "add_context",
        add_context,
        ToolDefinition(
            name="add_context",
            description=(
                "Attach user context to an entity — e.g. 'we are in a dispute "
                "with this tenant' or 'this property is being renovated'."
            ),
            args=[
                ToolArg(name="entity_type", description="Entity type name", required=True),
                ToolArg(name="entity_id", description="Entity ID to annotate", required=True),
                ToolArg(name="context", description="Context text to attach", required=True),
            ],
        ),
    )
