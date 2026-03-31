"""Shared value objects used across domain submodules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datetime import datetime


class TimeWindow(BaseModel, frozen=True):
    start: datetime
    end: datetime

    def contains(self, dt: datetime) -> bool:
        return self.start <= dt <= self.end

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()


class EntityRef(BaseModel, frozen=True):
    """A lightweight reference to a domain entity (e.g., a property, a tenant, a unit)."""

    entity_type: str
    entity_id: str
    label: str | None = Field(default=None)
