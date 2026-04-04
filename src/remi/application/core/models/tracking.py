"""Tracking — director follow-up.

ActionItem, Note.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from remi.application.core.models._helpers import _utcnow
from remi.application.core.models.enums import (
    ActionItemPriority,
    ActionItemStatus,
    NoteProvenance,
)


class ActionItem(BaseModel, frozen=True):
    """User-created action item tied to a manager, property, or tenant."""

    id: str
    title: str
    description: str = ""
    status: ActionItemStatus = ActionItemStatus.OPEN
    priority: ActionItemPriority = ActionItemPriority.MEDIUM
    manager_id: str | None = None
    property_id: str | None = None
    tenant_id: str | None = None
    due_date: date | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Note(BaseModel, frozen=True):
    """A note attached to any domain entity.

    Provenance distinguishes user-entered notes from report-derived or
    AI-inferred observations. Notes are first-class domain objects stored
    in the property store and surfaced into the knowledge graph via the bridge.
    """

    id: str
    content: str
    entity_type: str
    entity_id: str
    provenance: NoteProvenance = NoteProvenance.USER_STATED
    source_doc: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
