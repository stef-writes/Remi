"""REST endpoints for leases."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from remi.interfaces.api.dependencies import get_container
from remi.interfaces.api.leases.schemas import ExpiringLeaseItem, ExpiringLeasesResponse

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(prefix="/leases", tags=["leases"])


@router.get("/expiring", response_model=ExpiringLeasesResponse)
async def expiring_leases(
    days: int = 60,
    container: Container = Depends(get_container),
) -> ExpiringLeasesResponse:
    result = await container.lease_query.expiring_leases(days=days)
    return ExpiringLeasesResponse(
        days_window=result.days_window,
        count=result.count,
        leases=[
            ExpiringLeaseItem(**item.model_dump()) for item in result.leases
        ],
    )
