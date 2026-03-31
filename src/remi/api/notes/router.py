"""REST endpoints for entity-generic notes backed by the KnowledgeGraph.

Notes are stored as ``Note`` entities in the ``ontology`` namespace of the
knowledge graph, linked to their subject via ``HAS_NOTE``.  Provenance
distinguishes user-entered notes (``user_stated``) from report-derived
(``data_derived``) and AI-generated (``inferred``) notes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from remi.api.dependencies import get_knowledge_graph
from remi.knowledge.ontology_bridge import BridgedKnowledgeGraph

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


def _note_resp(obj: dict) -> NoteResponse:
    return NoteResponse(
        id=obj.get("id", ""),
        content=obj.get("content", ""),
        entity_type=obj.get("entity_type", ""),
        entity_id=obj.get("entity_id", ""),
        provenance=obj.get("provenance", "user_stated"),
        source_doc=obj.get("source_doc"),
        created_by=obj.get("created_by"),
        created_at=obj.get("created_at"),
        updated_at=obj.get("updated_at"),
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
    return _note_resp({"id": note_id, **props})


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    body: NoteUpdateRequest,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> NoteResponse:
    existing = await kg.get_object("Note", note_id)
    if not existing:
        raise HTTPException(404, f"Note '{note_id}' not found")

    now = datetime.now(UTC).isoformat()
    updated_props = {**existing, "content": body.content, "updated_at": now}
    updated_props.pop("id", None)
    await kg.put_object("Note", note_id, updated_props)
    return _note_resp({"id": note_id, **updated_props})


@router.delete("/{note_id}", status_code=200)
async def delete_note(
    note_id: str,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> dict[str, bool]:
    existing = await kg.get_object("Note", note_id)
    if not existing:
        raise HTTPException(404, f"Note '{note_id}' not found")

    from remi.models.memory import Entity

    ks = kg._ks  # noqa: SLF001
    deleted = await ks.delete_entity("ontology", note_id)
    if not deleted:
        raise HTTPException(404, f"Note '{note_id}' not found")
    return {"deleted": True}
