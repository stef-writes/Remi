"""Intelligence mutations — assertion tools, search tools, workflow tools."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import structlog

from typing import Any

from remi.agent.events import DomainEvent, EventBus
from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry
from remi.application.core.events import (
    ChangeEvent,
    ChangeSet,
    ChangeSource,
    ChangeType,
    EventStore,
    FieldChange,
)
from remi.application.core.protocols import PropertyStore

_log = structlog.get_logger(__name__)


async def _assert_fact(
    ps: PropertyStore,
    event_store: EventStore | None,
    event_bus: EventBus | None,
    *,
    entity_type: str,
    entity_id: str | None = None,
    properties: dict[str, str],
    related_to: str | None = None,
    relation_type: str | None = None,
) -> dict[str, str]:
    """Assert a new fact by creating a Note on PropertyStore."""
    from remi.application.core.models import Note

    eid = entity_id or f"{entity_type.lower()}:{uuid4().hex[:12]}"
    note_id = f"assertion:{uuid4().hex[:12]}"
    content_parts = [f"Asserted {entity_type} fact:"]
    for k, v in properties.items():
        content_parts.append(f"  {k}: {v}")
    if related_to and relation_type:
        content_parts.append(f"  Related: {relation_type} -> {related_to}")

    note = Note(
        id=note_id,
        content="\n".join(content_parts),
        entity_type=entity_type,
        entity_id=eid,
        tags=["assertion", "user"],
    )
    await ps.upsert_note(note)

    if event_store is not None:
        now = datetime.now(UTC)
        cs = ChangeSet(
            source=ChangeSource.AGENT_ASSERTION,
            source_detail=f"assert_fact:{entity_type}",
            timestamp=now,
            created=[
                ChangeEvent(
                    entity_type=entity_type,
                    entity_id=eid,
                    change_type=ChangeType.CREATED,
                    fields=tuple(FieldChange(field=k, new_value=v) for k, v in properties.items()),
                    source=ChangeSource.AGENT_ASSERTION,
                    timestamp=now,
                ),
            ],
        )
        await event_store.append(cs)

    if event_bus is not None:
        await event_bus.publish(DomainEvent(
            topic="assertion.created",
            source="tools.assertions",
            payload={
                "entity_type": entity_type,
                "entity_id": eid,
                "properties": properties,
            },
        ))

    _log.info("user_fact_asserted", entity_type=entity_type, entity_id=eid)
    return {"status": "asserted", "entity_id": eid, "entity_type": entity_type}


async def _add_context(
    ps: PropertyStore,
    *,
    entity_type: str,
    entity_id: str,
    context: str,
) -> dict[str, str]:
    """Attach a user-context annotation as a Note."""
    from remi.application.core.models import Note

    note_id = f"context:{uuid4().hex[:12]}"
    note = Note(
        id=note_id,
        content=context,
        entity_type=entity_type,
        entity_id=entity_id,
        tags=["user_context"],
    )
    await ps.upsert_note(note)

    _log.info(
        "user_context_added",
        entity_type=entity_type,
        entity_id=entity_id,
        note_id=note_id,
    )
    return {"status": "context_added", "note_id": note_id, "entity_id": entity_id}


class AssertionToolProvider(ToolProvider):
    def __init__(
        self,
        property_store: PropertyStore,
        event_store: EventStore | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._property_store = property_store
        self._event_store = event_store
        self._event_bus = event_bus

    def register(self, registry: ToolRegistry) -> None:
        """Register user-assertion tools on the agent tool registry."""
        ps = self._property_store
        event_store = self._event_store
        event_bus = self._event_bus

        async def assert_fact(
            entity_type: str,
            properties: dict[str, str],
            entity_id: str | None = None,
            related_to: str | None = None,
            relation_type: str | None = None,
        ) -> dict[str, str]:
            """Assert a new fact."""
            return await _assert_fact(
                ps,
                event_store,
                event_bus,
                entity_type=entity_type,
                entity_id=entity_id,
                properties=properties,
                related_to=related_to,
                relation_type=relation_type,
            )

        async def add_context(
            entity_type: str,
            entity_id: str,
            context: str,
        ) -> dict[str, str]:
            """Attach user context to an entity."""
            return await _add_context(
                ps,
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
                    "Record a new fact or observation. Creates a note with "
                    "user-level provenance (highest confidence). Optionally "
                    "note a relationship to an existing entity."
                ),
                args=[
                    ToolArg(name="entity_type", description="Entity type name", required=True),
                    ToolArg(
                        name="properties",
                        description="Entity properties as JSON",
                        type="object",
                        required=True,
                    ),
                    ToolArg(name="entity_id", description="Optional entity ID"),
                    ToolArg(name="related_to", description="ID of entity to link to"),
                    ToolArg(name="relation_type", description="Link type for relation"),
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
