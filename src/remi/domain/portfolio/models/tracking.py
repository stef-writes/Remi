"""Tracking — director follow-up.

ActionItem.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from remi.domain.portfolio.models._helpers import _utcnow
from remi.domain.portfolio.models.enums import ActionItemPriority, ActionItemStatus


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
