"""Event log REST endpoints — observe ChangeSets flowing through the system.

Exposes the EventStore as a read-only API so you can:
- List recent ChangeSets across all uploads
- Inspect a specific ChangeSet by ID
- Query the change history for a specific entity
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from remi.shell.api.dependencies import Ctr
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/events", tags=["events"])


def _changeset_to_dict(cs: object) -> dict[str, Any]:
    """Serialize a ChangeSet dataclass to a JSON-safe dict."""
    from remi.application.core.events import ChangeSet

    assert isinstance(cs, ChangeSet)
    return {
        "id": cs.id,
        "source": cs.source.value,
        "source_detail": cs.source_detail,
        "adapter_name": cs.adapter_name,
        "report_type": cs.report_type,
        "document_id": cs.document_id,
        "timestamp": cs.timestamp.isoformat(),
        "summary": cs.summary(),
        "total_changes": cs.total_changes,
        "is_empty": cs.is_empty,
        "events": [
            {
                "entity_type": ev.entity_type,
                "entity_id": ev.entity_id,
                "change_type": ev.change_type.value,
                "source": ev.source.value,
                "timestamp": ev.timestamp.isoformat(),
                "fields": [
                    {
                        "field": fc.field,
                        "old_value": fc.old_value,
                        "new_value": fc.new_value,
                    }
                    for fc in ev.fields
                ],
            }
            for ev in cs.events
        ],
        "unchanged_ids": cs.unchanged_ids,
    }


@router.get("")
async def list_recent_events(
    c: Ctr,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """List the most recent ChangeSets across all sources."""
    changesets = await c.event_store.list_recent(limit=limit)
    return {
        "count": len(changesets),
        "changesets": [_changeset_to_dict(cs) for cs in changesets],
    }


@router.get("/{changeset_id}")
async def get_changeset(
    changeset_id: str,
    c: Ctr,
) -> dict[str, Any]:
    """Retrieve a specific ChangeSet by ID."""
    cs = await c.event_store.get(changeset_id)
    if cs is None:
        raise NotFoundError("ChangeSet", changeset_id)
    return _changeset_to_dict(cs)


@router.get("/entity/{entity_id}")
async def entity_history(
    entity_id: str,
    c: Ctr,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """List ChangeSets that touched a specific entity."""
    changesets = await c.event_store.list_by_entity(entity_id, limit=limit)
    return {
        "entity_id": entity_id,
        "count": len(changesets),
        "changesets": [_changeset_to_dict(cs) for cs in changesets],
    }
