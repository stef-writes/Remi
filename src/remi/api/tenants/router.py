"""REST endpoints for tenant queries."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from remi.api.dependencies import get_property_store
from remi.models.properties import PropertyStore

router = APIRouter(prefix="/tenants", tags=["tenants"])


class LeaseInfo(BaseModel, frozen=True):
    lease_id: str
    unit: str
    property_id: str
    start: str
    end: str
    monthly_rent: float
    status: str


class TenantDetailResponse(BaseModel, frozen=True):
    tenant_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    leases: list[LeaseInfo]


@router.get("/{tenant_id}", response_model=TenantDetailResponse)
async def get_tenant(
    tenant_id: str,
    ps: PropertyStore = Depends(get_property_store),
) -> TenantDetailResponse:
    tenant = await ps.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(404, f"Tenant '{tenant_id}' not found")
    leases = await ps.list_leases(tenant_id=tenant_id)
    lease_info: list[LeaseInfo] = []
    for le in leases:
        unit = await ps.get_unit(le.unit_id)
        lease_info.append(
            LeaseInfo(
                lease_id=le.id,
                unit=unit.unit_number if unit else le.unit_id,
                property_id=le.property_id,
                start=le.start_date.isoformat(),
                end=le.end_date.isoformat(),
                monthly_rent=float(le.monthly_rent),
                status=le.status.value,
            )
        )
    return TenantDetailResponse(
        tenant_id=tenant_id,
        name=tenant.name,
        email=tenant.email,
        phone=tenant.phone,
        leases=lease_info,
    )
