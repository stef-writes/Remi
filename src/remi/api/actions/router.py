"""REST endpoints for action items and manager notes (review prep).

Action items: PropertyStore (SQL-backed).
Manager notes: KnowledgeGraph (graph-backed Note entities with entity_type=PropertyManager).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from remi.api.dependencies import get_knowledge_graph, get_property_store
from remi.knowledge.ontology_bridge import BridgedKnowledgeGraph
from remi.models.properties import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
    PropertyStore,
)

router = APIRouter(prefix="/actions", tags=["actions"])


# ---------------------------------------------------------------------------
# Action Items
# ---------------------------------------------------------------------------


class ActionItemCreate(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    manager_id: str | None = None
    property_id: str | None = None
    tenant_id: str | None = None
    due_date: date | None = None


class ActionItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: date | None = None


class ActionItemResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: str
    manager_id: str | None
    property_id: str | None
    tenant_id: str | None
    due_date: str | None
    created_at: str
    updated_at: str


class ActionItemListResponse(BaseModel):
    items: list[ActionItemResponse]
    total: int


def _ai_resp(item: ActionItem) -> ActionItemResponse:
    return ActionItemResponse(
        id=item.id,
        title=item.title,
        description=item.description,
        status=item.status.value,
        priority=item.priority.value,
        manager_id=item.manager_id,
        property_id=item.property_id,
        tenant_id=item.tenant_id,
        due_date=item.due_date.isoformat() if item.due_date else None,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.get("/items", response_model=ActionItemListResponse)
async def list_action_items(
    manager_id: str | None = None,
    property_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
    ps: PropertyStore = Depends(get_property_store),
) -> ActionItemListResponse:
    ai_status = ActionItemStatus(status) if status else None
    items = await ps.list_action_items(
        manager_id=manager_id,
        property_id=property_id,
        tenant_id=tenant_id,
        status=ai_status,
    )
    items.sort(key=lambda i: i.created_at, reverse=True)
    return ActionItemListResponse(items=[_ai_resp(i) for i in items], total=len(items))


@router.post("/items", response_model=ActionItemResponse, status_code=201)
async def create_action_item(
    body: ActionItemCreate,
    ps: PropertyStore = Depends(get_property_store),
) -> ActionItemResponse:
    item = ActionItem(
        id=f"action:{uuid.uuid4().hex[:12]}",
        title=body.title,
        description=body.description,
        priority=ActionItemPriority(body.priority),
        manager_id=body.manager_id,
        property_id=body.property_id,
        tenant_id=body.tenant_id,
        due_date=body.due_date,
    )
    await ps.upsert_action_item(item)
    return _ai_resp(item)


@router.patch("/items/{item_id}", response_model=ActionItemResponse)
async def update_action_item(
    item_id: str,
    body: ActionItemUpdate,
    ps: PropertyStore = Depends(get_property_store),
) -> ActionItemResponse:
    existing = await ps.get_action_item(item_id)
    if not existing:
        raise HTTPException(404, f"Action item '{item_id}' not found")

    updates: dict[str, object] = {"updated_at": datetime.now(UTC)}
    if body.title is not None:
        updates["title"] = body.title
    if body.description is not None:
        updates["description"] = body.description
    if body.status is not None:
        updates["status"] = ActionItemStatus(body.status)
    if body.priority is not None:
        updates["priority"] = ActionItemPriority(body.priority)
    if body.due_date is not None:
        updates["due_date"] = body.due_date

    updated = existing.model_copy(update=updates)
    await ps.upsert_action_item(updated)
    return _ai_resp(updated)


@router.delete("/items/{item_id}", status_code=200)
async def delete_action_item(
    item_id: str,
    ps: PropertyStore = Depends(get_property_store),
) -> dict[str, bool]:
    deleted = await ps.delete_action_item(item_id)
    if not deleted:
        raise HTTPException(404, f"Action item '{item_id}' not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Manager Notes — backed by KnowledgeGraph Note entities
# ---------------------------------------------------------------------------


class NoteCreate(BaseModel):
    manager_id: str
    content: str


class NoteUpdate(BaseModel):
    content: str


class NoteResponse(BaseModel):
    id: str
    manager_id: str
    content: str
    created_at: str
    updated_at: str


class NoteListResponse(BaseModel):
    notes: list[NoteResponse]
    total: int


def _note_resp_from_graph(obj: dict) -> NoteResponse:
    return NoteResponse(
        id=obj.get("id", ""),
        manager_id=obj.get("entity_id", ""),
        content=obj.get("content", ""),
        created_at=obj.get("created_at", ""),
        updated_at=obj.get("updated_at", ""),
    )


@router.get("/notes", response_model=NoteListResponse)
async def list_notes(
    manager_id: str = Query(...),
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> NoteListResponse:
    results = await kg.search_objects(
        "Note",
        filters={"entity_type": "PropertyManager", "entity_id": manager_id},
        limit=200,
    )
    notes = [_note_resp_from_graph(r) for r in results]
    notes.sort(key=lambda n: n.created_at, reverse=True)
    return NoteListResponse(notes=notes, total=len(notes))


@router.post("/notes", response_model=NoteResponse, status_code=201)
async def create_note(
    body: NoteCreate,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> NoteResponse:
    note_id = f"note:{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()
    props = {
        "content": body.content,
        "entity_type": "PropertyManager",
        "entity_id": body.manager_id,
        "provenance": "user_stated",
        "created_at": now,
        "updated_at": now,
    }
    await kg.put_object("Note", note_id, props)
    await kg.put_link(body.manager_id, "HAS_NOTE", note_id)
    return _note_resp_from_graph({"id": note_id, **props})


@router.patch("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    body: NoteUpdate,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> NoteResponse:
    existing = await kg.get_object("Note", note_id)
    if not existing:
        raise HTTPException(404, f"Note '{note_id}' not found")

    now = datetime.now(UTC).isoformat()
    updated_props = {**existing, "content": body.content, "updated_at": now}
    updated_props.pop("id", None)
    await kg.put_object("Note", note_id, updated_props)
    return _note_resp_from_graph({"id": note_id, **updated_props})


@router.delete("/notes/{note_id}", status_code=200)
async def delete_note(
    note_id: str,
    kg: BridgedKnowledgeGraph = Depends(get_knowledge_graph),
) -> dict[str, bool]:
    existing = await kg.get_object("Note", note_id)
    if not existing:
        raise HTTPException(404, f"Note '{note_id}' not found")
    ks = kg._ks  # noqa: SLF001
    deleted = await ks.delete_entity("ontology", note_id)
    if not deleted:
        raise HTTPException(404, f"Note '{note_id}' not found")
    return {"deleted": True}
