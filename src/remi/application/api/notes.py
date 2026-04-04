"""REST endpoints for entity-generic notes.

Notes are first-class domain entities stored via NoteRepository (part of
PropertyStore). The knowledge graph still surfaces them via the bridge —
the store is now the source of truth, not KnowledgeStore.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from remi.application.core.models import Note, NoteProvenance
from remi.application.core.protocols import NoteRepository
from remi.application.api.dependencies import get_property_store
from remi.application.api.shared_schemas import DeletedResponse
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreateRequest(BaseModel):
    content: str
    entity_type: str
    entity_id: str
    provenance: NoteProvenance = NoteProvenance.USER_STATED
    source_doc: str | None = None
    created_by: str | None = None


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
    created_at: str
    updated_at: str


class NoteListResponse(BaseModel):
    notes: list[NoteResponse]
    total: int


class BatchNoteRequest(BaseModel):
    entity_type: str
    entity_ids: list[str]


class BatchNoteResponse(BaseModel):
    notes_by_entity: dict[str, list[NoteResponse]]


def _note_resp(note: Note) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        content=note.content,
        entity_type=note.entity_type,
        entity_id=note.entity_id,
        provenance=note.provenance.value,
        source_doc=note.source_doc,
        created_by=note.created_by,
        created_at=note.created_at.isoformat(),
        updated_at=note.updated_at.isoformat(),
    )


@router.get("", response_model=NoteListResponse)
async def list_notes(
    entity_type: str,
    entity_id: str,
    store: NoteRepository = Depends(get_property_store),
) -> NoteListResponse:
    notes = await store.list_notes(entity_type=entity_type, entity_id=entity_id)
    notes.sort(key=lambda n: n.created_at, reverse=True)
    return NoteListResponse(notes=[_note_resp(n) for n in notes], total=len(notes))


@router.post("/batch", response_model=BatchNoteResponse)
async def batch_notes(
    body: BatchNoteRequest,
    store: NoteRepository = Depends(get_property_store),
) -> BatchNoteResponse:
    """Fetch notes for multiple entities in a single round trip."""
    by_entity: dict[str, list[NoteResponse]] = {eid: [] for eid in body.entity_ids}
    for entity_id in body.entity_ids:
        notes = await store.list_notes(entity_type=body.entity_type, entity_id=entity_id)
        notes.sort(key=lambda n: n.created_at, reverse=True)
        by_entity[entity_id] = [_note_resp(n) for n in notes]
    return BatchNoteResponse(notes_by_entity=by_entity)


@router.post("", response_model=NoteResponse, status_code=201)
async def create_note(
    body: NoteCreateRequest,
    store: NoteRepository = Depends(get_property_store),
) -> NoteResponse:
    now = datetime.now(UTC)
    note = Note(
        id=f"note:{uuid.uuid4().hex[:12]}",
        content=body.content,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        provenance=body.provenance,
        source_doc=body.source_doc,
        created_by=body.created_by,
        created_at=now,
        updated_at=now,
    )
    result = await store.upsert_note(note)
    return _note_resp(result.entity)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    body: NoteUpdateRequest,
    store: NoteRepository = Depends(get_property_store),
) -> NoteResponse:
    existing = await store.get_note(note_id)
    if not existing:
        raise NotFoundError("Note", note_id)
    updated = existing.model_copy(update={"content": body.content, "updated_at": datetime.now(UTC)})
    result = await store.upsert_note(updated)
    return _note_resp(result.entity)


@router.delete("/{note_id}", status_code=200)
async def delete_note(
    note_id: str,
    store: NoteRepository = Depends(get_property_store),
) -> DeletedResponse:
    existing = await store.get_note(note_id)
    if not existing:
        raise NotFoundError("Note", note_id)
    await store.delete_note(note_id)
    return DeletedResponse()
