"""First-class view model contracts for UI-ready module outputs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DashboardCard(BaseModel, frozen=True):
    """A single KPI card for dashboard rendering."""

    title: str
    value: str | float
    unit: str | None = None
    trend: str | None = None
    trend_direction: str | None = None  # "up" | "down" | "flat"
    severity: str | None = None  # "info" | "warning" | "critical"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TableColumn(BaseModel, frozen=True):
    key: str
    label: str
    data_type: str = "string"
    sortable: bool = True


class TableView(BaseModel, frozen=True):
    """A tabular data view for list/grid rendering."""

    title: str
    columns: list[TableColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 50
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProfileField(BaseModel, frozen=True):
    label: str
    value: Any
    data_type: str = "string"


class ProfileSection(BaseModel, frozen=True):
    heading: str
    fields: list[ProfileField] = Field(default_factory=list)


class ProfileView(BaseModel, frozen=True):
    """A detail/profile view for a single entity."""

    title: str
    entity_type: str
    entity_id: str
    sections: list[ProfileSection] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
