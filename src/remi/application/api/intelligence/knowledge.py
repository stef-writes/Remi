"""Knowledge graph assertion endpoints — assert, correct, contextualize.

REST surface for user writes to the knowledge graph. Same operations
available as agent tools in ``application/tools/assertions.py``.

All mutation endpoints produce ``ChangeSet`` events through the
``EventStore`` so corrections flow through the same event pipeline
as adapter imports, keeping DB and ontology in sync.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from remi.application.tools.assertions import _add_context, _assert_fact, _correct_entity
from remi.shell.api.dependencies import Ctr

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class AssertFactRequest(BaseModel):
    entity_type: str
    entity_id: str | None = None
    properties: dict[str, str]
    related_to: str | None = None
    relation_type: str | None = None


class CorrectEntityRequest(BaseModel):
    entity_type: str
    entity_id: str
    corrections: dict[str, str]


class AddContextRequest(BaseModel):
    entity_type: str
    entity_id: str
    context: str


@router.post("/assert")
async def assert_fact(
    body: AssertFactRequest,
    c: Ctr,
) -> dict[str, str]:
    """Assert a new fact into the knowledge graph with user provenance."""
    return await _assert_fact(
        c.knowledge_graph,
        c.event_store,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        properties=body.properties,
        related_to=body.related_to,
        relation_type=body.relation_type,
    )


@router.post("/correct")
async def correct_entity(
    body: CorrectEntityRequest,
    c: Ctr,
) -> dict[str, str]:
    """Correct field values on an existing entity."""
    return await _correct_entity(
        c.knowledge_graph,
        c.event_store,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        corrections=body.corrections,
    )


@router.post("/context")
async def add_context(
    body: AddContextRequest,
    c: Ctr,
) -> dict[str, str]:
    """Attach user context/annotation to an entity."""
    return await _add_context(
        c.knowledge_graph,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        context=body.context,
    )
