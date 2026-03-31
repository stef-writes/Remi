"""REST endpoints for maintenance requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from remi.api.dependencies import get_maintenance_query
from remi.api.maintenance.schemas import (
    MaintenanceItem,
    MaintenanceListResponse,
    MaintenanceSummaryResponse,
)
from remi.services.maintenance_queries import MaintenanceQueryService

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("", response_model=MaintenanceListResponse)
async def list_requests(
    property_id: str | None = None,
    status: str | None = None,
    svc: MaintenanceQueryService = Depends(get_maintenance_query),
) -> MaintenanceListResponse:
    result = await svc.list_requests(property_id=property_id, status=status)
    return MaintenanceListResponse(
        count=result.count,
        requests=[MaintenanceItem(**r.model_dump()) for r in result.requests],
    )


@router.get("/summary", response_model=MaintenanceSummaryResponse)
async def maintenance_summary(
    property_id: str | None = None,
    svc: MaintenanceQueryService = Depends(get_maintenance_query),
) -> MaintenanceSummaryResponse:
    result = await svc.maintenance_summary(property_id=property_id)
    return MaintenanceSummaryResponse(**result.model_dump())
