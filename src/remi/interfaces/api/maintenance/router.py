"""REST endpoints for maintenance requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from remi.interfaces.api.dependencies import get_container
from remi.interfaces.api.maintenance.schemas import (
    MaintenanceItem,
    MaintenanceListResponse,
    MaintenanceSummaryResponse,
)

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("", response_model=MaintenanceListResponse)
async def list_requests(
    property_id: str | None = None,
    status: str | None = None,
    container: Container = Depends(get_container),
) -> MaintenanceListResponse:
    result = await container.maintenance_query.list_requests(
        property_id=property_id, status=status
    )
    return MaintenanceListResponse(
        count=result.count,
        requests=[MaintenanceItem(**r.model_dump()) for r in result.requests],
    )


@router.get("/summary", response_model=MaintenanceSummaryResponse)
async def maintenance_summary(
    property_id: str | None = None,
    container: Container = Depends(get_container),
) -> MaintenanceSummaryResponse:
    result = await container.maintenance_query.maintenance_summary(property_id=property_id)
    return MaintenanceSummaryResponse(**result.model_dump())
