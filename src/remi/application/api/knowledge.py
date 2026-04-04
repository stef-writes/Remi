"""Knowledge graph assertion endpoints — assert, correct, contextualize.

REST surface for user writes to the knowledge graph. Same operations
available as agent tools in ``application/tools/assertions.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from remi.application.tools.assertions import _add_context, _assert_fact, _correct_entity

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


def _kg(request: Request) -> Any:
    return request.app.state.container.knowledge_graph


@router.post("/assert")
async def assert_fact(body: AssertFactRequest, request: Request) -> dict[str, str]:
    """Assert a new fact into the knowledge graph with user provenance."""
    return await _assert_fact(
        _kg(request),
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        properties=body.properties,
        related_to=body.related_to,
        relation_type=body.relation_type,
    )


@router.post("/correct")
async def correct_entity(body: CorrectEntityRequest, request: Request) -> dict[str, str]:
    """Correct field values on an existing entity."""
    return await _correct_entity(
        _kg(request),
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        corrections=body.corrections,
    )


@router.post("/context")
async def add_context(body: AddContextRequest, request: Request) -> dict[str, str]:
    """Attach user context/annotation to an entity."""
    return await _add_context(
        _kg(request),
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        context=body.context,
    )
