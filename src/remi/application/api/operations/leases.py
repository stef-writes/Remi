"""REST endpoints for leases."""

from __future__ import annotations

from fastapi import APIRouter

from remi.application.portfolio import (
    ExpiringLeasesResult,
    LeaseListResult,
)
from remi.shell.api.dependencies import Ctr

router = APIRouter(prefix="/leases", tags=["leases"])


@router.get("", response_model=LeaseListResult)
async def list_leases(
    c: Ctr,
    property_id: str | None = None,
    status: str | None = None,
) -> LeaseListResult:
    return await c.lease_resolver.list_leases(property_id=property_id, status=status)


@router.get("/expiring", response_model=ExpiringLeasesResult)
async def expiring_leases(
    c: Ctr,
    days: int = 60,
) -> ExpiringLeasesResult:
    return await c.lease_resolver.expiring_leases(days=days)
