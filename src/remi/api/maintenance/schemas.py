"""Response schemas for maintenance."""

from __future__ import annotations

from pydantic import BaseModel


class MaintenanceItem(BaseModel):
    id: str
    property_id: str
    unit_id: str
    title: str
    category: str
    priority: str
    status: str
    cost: float | None
    created: str
    resolved: str | None


class MaintenanceListResponse(BaseModel):
    count: int
    requests: list[MaintenanceItem]


class MaintenanceSummaryResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    total_cost: float
