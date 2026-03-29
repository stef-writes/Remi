"""MaintenanceQueryService — maintenance listing and summary aggregation.

Pure PropertyStore read-model.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from remi.domain.properties.enums import MaintenanceStatus
from remi.domain.properties.ports import PropertyStore


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

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


class MaintenanceListResult(BaseModel):
    count: int
    requests: list[MaintenanceItem]


class MaintenanceSummaryResult(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    total_cost: float


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MaintenanceQueryService:
    """Maintenance listing and summary read models."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_requests(
        self,
        property_id: str | None = None,
        status: str | None = None,
    ) -> MaintenanceListResult:
        maint_status = MaintenanceStatus(status) if status else None
        requests = await self._ps.list_maintenance_requests(
            property_id=property_id, status=maint_status
        )
        requests.sort(key=lambda r: r.created_at, reverse=True)

        return MaintenanceListResult(
            count=len(requests),
            requests=[
                MaintenanceItem(
                    id=r.id,
                    property_id=r.property_id,
                    unit_id=r.unit_id,
                    title=r.title,
                    category=r.category.value,
                    priority=r.priority.value,
                    status=r.status.value,
                    cost=float(r.cost) if r.cost else None,
                    created=r.created_at.isoformat(),
                    resolved=r.resolved_at.isoformat() if r.resolved_at else None,
                )
                for r in requests
            ],
        )

    async def maintenance_summary(
        self, property_id: str | None = None
    ) -> MaintenanceSummaryResult:
        requests = await self._ps.list_maintenance_requests(property_id=property_id)

        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        total_cost = Decimal("0")

        for r in requests:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
            by_category[r.category.value] = by_category.get(r.category.value, 0) + 1
            if r.cost:
                total_cost += r.cost

        return MaintenanceSummaryResult(
            total=len(requests),
            by_status=by_status,
            by_category=by_category,
            total_cost=float(total_cost),
        )
