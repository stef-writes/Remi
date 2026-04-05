"""REST endpoints for action items.

Action items are stored via PropertyStore (SQL-backed).
Manager notes have moved to the dedicated /notes router (NoteRepository).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from remi.application.api.shared_schemas import DeletedResponse
from remi.application.core.models import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
)
from remi.shell.api.dependencies import Ctr
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/actions", tags=["actions"])


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
    c: Ctr,
    manager_id: str | None = None,
    property_id: str | None = None,
    tenant_id: str | None = None,
    status: str | None = None,
) -> ActionItemListResponse:
    ai_status = ActionItemStatus(status) if status else None
    items = await c.property_store.list_action_items(
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
    c: Ctr,
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
    await c.property_store.upsert_action_item(item)
    return _ai_resp(item)


@router.patch("/items/{item_id}", response_model=ActionItemResponse)
async def update_action_item(
    item_id: str,
    body: ActionItemUpdate,
    c: Ctr,
) -> ActionItemResponse:
    existing = await c.property_store.get_action_item(item_id)
    if not existing:
        raise NotFoundError("ActionItem", item_id)

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
    await c.property_store.upsert_action_item(updated)
    return _ai_resp(updated)


@router.delete("/items/{item_id}", status_code=200)
async def delete_action_item(
    item_id: str,
    c: Ctr,
) -> DeletedResponse:
    deleted = await c.property_store.delete_action_item(item_id)
    if not deleted:
        raise NotFoundError("ActionItem", item_id)
    return DeletedResponse()
