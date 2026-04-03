"""REST endpoints for entity-generic notes backed by the KnowledgeGraph.

Notes are stored as ``Note`` entities in the ``ontology`` namespace of the
knowledge graph, linked to their subject via ``HAS_NOTE``.  Provenance
distinguishes user-entered notes (``user_stated``) from report-derived
(``data_derived``) and AI-generated (``inferred``) notes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from remi.types.errors import NotFoundError
from remi.agent.graph.bridge import BridgedKnowledgeGraph
from remi.agent.graph.types import GraphObject
from remi.shell.api.dependencies import get_knowledge_graph
from remi.shell.api.schemas import DeletedResponse

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreateRequest(BaseModel):
    content: str
    entity_type: str
    entity_id: str


class NoteUpdateRequest(BaseModel):
    content: str


class NoteResponse(BaseModel):
    id: str
    content: str
    entity_type: str
    entity_id: str
    provenance: str
    source_doc: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class NoteListResponse(BaseModel):
    notes: list[NoteResponse]
    total: int


class BatchNoteRequest(BaseModel):
    entity_type: str
    entity_ids: list[str]


class BatchNoteResponse(BaseModel):
    notes_by_entity: dict[str, list[NoteResponse]]


def _note_resp(obj: GraphObject) -> NoteResponse:
    return NoteResponse(
        id=obj.id,
        content=obj.properties.get("content", ""),
        entity_type=obj.properties.get("entity_type", ""),
        entity_id=obj.properties.get("entity_id", ""),
        provenance=obj.properties.get("provenance", "user_stated"),
        source_doc=obj.properties.get("source_doc"),
        created_by=obj.properties.get("created_by"),
        created_at=obj.properties.get("created_at"),
        updated_at=obj.properties.get("updated_at"),
    )


@router.get("", response_model=NoteListResponse)
async def list_notes(
    entity_type: str = Query(..., description="Type of entity (e.g. Tenant, PropertyManager)"),
    entity_id: str = Query(..., description="ID of the entity"),
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> NoteListResponse:
    results = await kg.search_objects(
        "Note",
        filters={"entity_type": entity_type, "entity_id": entity_id},
        limit=200,
    )
    notes = [_note_resp(r) for r in results]
    notes.sort(key=lambda n: n.created_at or "", reverse=True)
    return NoteListResponse(notes=notes, total=len(notes))


@router.post("/batch", response_model=BatchNoteResponse)
async def batch_notes(
    body: BatchNoteRequest,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> BatchNoteResponse:
    """Fetch notes for multiple entities in a single round trip."""
    all_notes = await kg.search_objects(
        "Note",
        filters={"entity_type": body.entity_type},
        limit=5000,
    )
    by_entity: dict[str, list[NoteResponse]] = {eid: [] for eid in body.entity_ids}
    for obj in all_notes:
        eid = obj.properties.get("entity_id", "")
        if eid in by_entity:
            by_entity[eid].append(_note_resp(obj))
    for notes in by_entity.values():
        notes.sort(key=lambda n: n.created_at or "", reverse=True)
    return BatchNoteResponse(notes_by_entity=by_entity)


@router.post("", response_model=NoteResponse, status_code=201)
async def create_note(
    body: NoteCreateRequest,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> NoteResponse:
    note_id = f"note:{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()
    props = {
        "content": body.content,
        "entity_type": body.entity_type,
        "entity_id": body.entity_id,
        "provenance": "user_stated",
        "created_at": now,
        "updated_at": now,
    }
    await kg.put_object("Note", note_id, props)
    await kg.put_link(body.entity_id, "HAS_NOTE", note_id)
    return _note_resp(GraphObject(id=note_id, type_name="Note", properties=props))


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    body: NoteUpdateRequest,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> NoteResponse:
    existing = await kg.get_object("Note", note_id)
    if not existing:
        raise NotFoundError("Note", note_id)

    now = datetime.now(UTC).isoformat()
    updated_props = {**existing.properties, "content": body.content, "updated_at": now}
    await kg.put_object("Note", note_id, updated_props)
    return _note_resp(GraphObject(id=note_id, type_name="Note", properties=updated_props))


@router.delete("/{note_id}", status_code=200)
async def delete_note(
    note_id: str,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> DeletedResponse:
    existing = await kg.get_object("Note", note_id)
    if not existing:
        raise NotFoundError("Note", note_id)

    deleted = await kg.delete_object("Note", note_id)
    if not deleted:
        raise NotFoundError("Note", note_id)
    return DeletedResponse()
