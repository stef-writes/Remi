"""REST endpoints for leases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from remi.api.dependencies import get_container
from remi.api.leases.schemas import (
    ExpiringLeaseItem,
    ExpiringLeasesResponse,
    LeaseListItem,
    LeaseListResponse,
)
from remi.models.properties import LeaseStatus

if TYPE_CHECKING:
    from remi.config.container import Container

router = APIRouter(prefix="/leases", tags=["leases"])


@router.get("", response_model=LeaseListResponse)
async def list_leases(
    property_id: str | None = None,
    status: str | None = None,
    container: Container = Depends(get_container),
) -> LeaseListResponse:
    lease_status = LeaseStatus(status) if status else None
    leases = await container.property_store.list_leases(
        property_id=property_id,
        status=lease_status,
    )
    items = []
    for le in leases:
        tenant = await container.property_store.get_tenant(le.tenant_id)
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
    container: Container = Depends(get_container),
) -> ExpiringLeasesResponse:
    result = await container.lease_query.expiring_leases(days=days)
    return ExpiringLeasesResponse(
        days_window=result.days_window,
        count=result.count,
        leases=[ExpiringLeaseItem(**item.model_dump()) for item in result.leases],
    )
