"""REST endpoints for maintenance requests."""

from __future__ import annotations

from fastapi import APIRouter

from remi.application.portfolio import (
    MaintenanceListResult,
    MaintenanceSummaryResult,
)
from remi.shell.api.dependencies import Ctr

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("", response_model=MaintenanceListResult)
async def list_requests(
    c: Ctr,
    property_id: str | None = None,
    status: str | None = None,
) -> MaintenanceListResult:
    return await c.maintenance_resolver.list_maintenance(property_id=property_id, status=status)


@router.get("/summary", response_model=MaintenanceSummaryResult)
async def maintenance_summary(
    c: Ctr,
    property_id: str | None = None,
) -> MaintenanceSummaryResult:
    return await c.maintenance_resolver.maintenance_summary(property_id=property_id)
