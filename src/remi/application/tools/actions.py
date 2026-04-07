"""Agent tools for action items and notes.

Provides: action_create, action_update, action_list, note_create.

Action items and notes both live in PropertyStore (SQL-backed).
The ProjectingPropertyStore syncs notes to the KnowledgeGraph automatically.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry
from remi.application.core.models import (
    ActionItem,
    ActionItemStatus,
    Note,
    NoteProvenance,
    Priority,
)
from remi.application.core.protocols import PropertyStore


class ActionToolProvider(ToolProvider):
    def __init__(
        self,
        property_store: PropertyStore,
        **_kwargs: Any,
    ) -> None:
        self._property_store = property_store

    def register(self, registry: ToolRegistry) -> None:
        ps = self._property_store

        async def action_create(args: dict[str, Any]) -> Any:
            item_id = f"ai-{uuid.uuid4().hex[:12]}"
            due: date | None = None
            if raw_due := args.get("due_date"):
                due = date.fromisoformat(str(raw_due))

            item = ActionItem(
                id=item_id,
                title=args["title"],
                description=args.get("description", ""),
                priority=Priority(args.get("priority", "medium")),
                manager_id=args.get("manager_id"),
                property_id=args.get("property_id"),
                tenant_id=args.get("tenant_id"),
                due_date=due,
            )
            await ps.upsert_action_item(item)
            return {
                "id": item.id,
                "title": item.title,
                "status": item.status.value,
                "created": True,
            }

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
                    ToolArg(
                        name="title",
                        description="Short title for the action item",
                        required=True,
                    ),
                    ToolArg(name="description", description="Detailed description"),
                    ToolArg(
                        name="priority",
                        description=(
                            "Priority: low, medium, high, urgent, emergency (default: medium)"
                        ),
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
                updates["priority"] = Priority(args["priority"])
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
                    ToolArg(
                        name="due_date",
                        description="New due date as YYYY-MM-DD (null to clear)",
                    ),
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

        # -- Notes (PropertyStore-backed, projected to KG automatically) -----------

        async def note_create(args: dict[str, Any]) -> Any:
            note_id = f"note:{uuid.uuid4().hex[:12]}"
            now = datetime.now(UTC)
            note = Note(
                id=note_id,
                content=args["content"],
                entity_type=args.get("entity_type", ""),
                entity_id=args.get("entity_id", ""),
                provenance=NoteProvenance.USER_STATED,
                created_by="agent",
                created_at=now,
                updated_at=now,
            )
            await ps.upsert_note(note)
            return {"id": note.id, "content": note.content, "created": True}

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
                    ToolArg(
                        name="entity_id",
                        description="ID of the entity this note is about",
                    ),
                ],
            ),
        )
