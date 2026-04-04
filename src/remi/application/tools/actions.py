"""Agent tools for action items and notes.

Provides: action_create, action_update, action_list, note_create.

Action items live in PropertyStore (SQL-backed, mutable workflow objects).
Notes live in KnowledgeGraph (graph-backed, provenance-tracked).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.types import ToolArg, ToolDefinition, ToolRegistry
from remi.application.core.models import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
)
from remi.application.core.protocols import PropertyStore


def register_action_tools(
    registry: ToolRegistry,
    *,
    property_store: PropertyStore,
    knowledge_graph: KnowledgeGraph | None = None,
) -> None:
    ps = property_store

    async def action_create(args: dict[str, Any]) -> Any:
        item_id = f"ai-{uuid.uuid4().hex[:12]}"
        due: date | None = None
        if raw_due := args.get("due_date"):
            due = date.fromisoformat(str(raw_due))

        item = ActionItem(
            id=item_id,
            title=args["title"],
            description=args.get("description", ""),
            priority=ActionItemPriority(args.get("priority", "medium")),
            manager_id=args.get("manager_id"),
            property_id=args.get("property_id"),
            tenant_id=args.get("tenant_id"),
            due_date=due,
        )
        await ps.upsert_action_item(item)
        return {"id": item.id, "title": item.title, "status": item.status.value, "created": True}

    registry.register(
        "action_create",
        action_create,
        ToolDefinition(
            name="action_create",
            description=(
                "Create an action item to track a follow-up for a manager, property, "
                "or tenant. Use when the director asks to be reminded about something "
                "or when you identify an issue that needs tracking."
            ),
            args=[
                ToolArg(name="title", description="Short title for the action item", required=True),
                ToolArg(name="description", description="Detailed description"),
                ToolArg(
                    name="priority",
                    description="Priority: low, medium, high, urgent (default: medium)",
                ),
                ToolArg(name="manager_id", description="Manager this relates to"),
                ToolArg(name="property_id", description="Property this relates to"),
                ToolArg(name="tenant_id", description="Tenant this relates to"),
                ToolArg(name="due_date", description="Due date as YYYY-MM-DD"),
            ],
        ),
    )

    async def action_update(args: dict[str, Any]) -> Any:
        item = await ps.get_action_item(args["item_id"])
        if not item:
            return {"error": f"Action item '{args['item_id']}' not found"}

        updates: dict[str, Any] = {}
        if "status" in args:
            updates["status"] = ActionItemStatus(args["status"])
        if "priority" in args:
            updates["priority"] = ActionItemPriority(args["priority"])
        if "title" in args:
            updates["title"] = args["title"]
        if "description" in args:
            updates["description"] = args["description"]
        if "due_date" in args:
            raw = args["due_date"]
            updates["due_date"] = date.fromisoformat(str(raw)) if raw else None

        updated = item.model_copy(update=updates)
        await ps.upsert_action_item(updated)
        return {
            "id": updated.id,
            "title": updated.title,
            "status": updated.status.value,
            "updated": True,
        }

    registry.register(
        "action_update",
        action_update,
        ToolDefinition(
            name="action_update",
            description=(
                "Update an existing action item — change status, priority, title, "
                "description, or due date."
            ),
            args=[
                ToolArg(
                    name="item_id",
                    description="ID of the action item to update",
                    required=True,
                ),
                ToolArg(
                    name="status",
                    description="New status: open, in_progress, done, cancelled",
                ),
                ToolArg(name="priority", description="New priority: low, medium, high, urgent"),
                ToolArg(name="title", description="New title"),
                ToolArg(name="description", description="New description"),
                ToolArg(name="due_date", description="New due date as YYYY-MM-DD (null to clear)"),
            ],
        ),
    )

    async def action_list(args: dict[str, Any]) -> Any:
        status = ActionItemStatus(args["status"]) if args.get("status") else None
        items = await ps.list_action_items(
            manager_id=args.get("manager_id"),
            property_id=args.get("property_id"),
            tenant_id=args.get("tenant_id"),
            status=status,
        )
        return [item.model_dump(mode="json") for item in items]

    registry.register(
        "action_list",
        action_list,
        ToolDefinition(
            name="action_list",
            description=(
                "List action items, optionally filtered by manager, property, tenant, "
                "or status. Returns structured action item data."
            ),
            args=[
                ToolArg(name="manager_id", description="Filter by manager ID"),
                ToolArg(name="property_id", description="Filter by property ID"),
                ToolArg(name="tenant_id", description="Filter by tenant ID"),
                ToolArg(
                    name="status",
                    description="Filter by status: open, in_progress, done, cancelled",
                ),
            ],
        ),
    )

    # -- Notes (KnowledgeGraph-backed) -----------------------------------------

    if knowledge_graph is not None:
        kg = knowledge_graph

        async def note_create(args: dict[str, Any]) -> Any:
            note_id = f"note:{uuid.uuid4().hex[:12]}"
            now = datetime.now(UTC).isoformat()
            props = {
                "content": args["content"],
                "entity_type": args.get("entity_type", ""),
                "entity_id": args.get("entity_id", ""),
                "provenance": "user_stated",
                "created_at": now,
                "updated_at": now,
            }
            await kg.put_object("Note", note_id, props)
            if entity_id := args.get("entity_id"):
                await kg.put_link(entity_id, "HAS_NOTE", note_id)
            return {"id": note_id, "content": props["content"], "created": True}

        registry.register(
            "note_create",
            note_create,
            ToolDefinition(
                name="note_create",
                description=(
                    "Create a note attached to a manager, property, tenant, or other "
                    "entity. Use when the director says to make a note about something "
                    "or when you want to record context for future reference."
                ),
                args=[
                    ToolArg(name="content", description="Note text", required=True),
                    ToolArg(
                        name="entity_type",
                        description="Type of entity (e.g. PropertyManager, Tenant, Property)",
                    ),
                    ToolArg(name="entity_id", description="ID of the entity this note is about"),
                ],
            ),
        )
