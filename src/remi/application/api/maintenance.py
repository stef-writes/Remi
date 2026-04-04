"""REST endpoints for maintenance requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from remi.application.services.queries import (
    MaintenanceListResult,
    MaintenanceSummaryResult,
    PortfolioQueryService,
)
from remi.application.api.dependencies import get_portfolio_query

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("", response_model=MaintenanceListResult)
async def list_requests(
    property_id: str | None = None,
    status: str | None = None,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> MaintenanceListResult:
    return await svc.list_maintenance(property_id=property_id, status=status)


@router.get("/summary", response_model=MaintenanceSummaryResult)
async def maintenance_summary(
    property_id: str | None = None,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> MaintenanceSummaryResult:
    return await svc.maintenance_summary(property_id=property_id)
