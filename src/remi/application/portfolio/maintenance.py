"""Maintenance — list and summary queries."""

from __future__ import annotations

from decimal import Decimal

from remi.application.core.models import MaintenanceStatus
from remi.application.core.protocols import PropertyStore

from ._models import (
    MaintenanceItem,
    MaintenanceListResult,
    MaintenanceSummaryResult,
)


class MaintenanceResolver:
    """Entity resolver for maintenance requests."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_maintenance(
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
