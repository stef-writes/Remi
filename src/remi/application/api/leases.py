"""REST endpoints for leases."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from remi.application.services.queries import PortfolioQueryService
from remi.application.api.schemas import (
    ExpiringLeasesResponse,
    LeaseListItem,
    LeaseListResponse,
)
from remi.application.core.models import LeaseStatus
from remi.application.core.protocols import PropertyStore
from remi.application.api.dependencies import get_portfolio_query, get_property_store

router = APIRouter(prefix="/leases", tags=["leases"])


@router.get("", response_model=LeaseListResponse)
async def list_leases(
    property_id: str | None = None,
    status: str | None = None,
    ps: PropertyStore = Depends(get_property_store),
) -> LeaseListResponse:
    lease_status = LeaseStatus(status) if status else None
    leases = await ps.list_leases(
        property_id=property_id,
        status=lease_status,
    )
    items = []
    for le in leases:
        tenant = await ps.get_tenant(le.tenant_id)
        items.append(
            LeaseListItem(
                id=le.id,
                tenant=tenant.name if tenant else le.tenant_id,
                unit_id=le.unit_id,
                property_id=le.property_id,
                start=le.start_date.isoformat(),
                end=le.end_date.isoformat(),
                rent=float(le.monthly_rent),
                status=le.status.value,
            )
        )
    return LeaseListResponse(count=len(items), leases=items)


@router.get("/expiring", response_model=ExpiringLeasesResponse)
async def expiring_leases(
    days: int = 60,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> ExpiringLeasesResponse:
    result = await svc.expiring_leases(days=days)
    return ExpiringLeasesResponse(
        days_window=result.days_window,
        count=result.count,
        leases=result.leases,
    )
