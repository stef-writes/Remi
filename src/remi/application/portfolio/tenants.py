"""Tenants — detail with lease history."""

from __future__ import annotations

from remi.application.core.protocols import PropertyStore

from ._models import LeaseInfo, TenantDetail


class TenantResolver:
    """Entity resolver for tenants."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def get_tenant_detail(self, tenant_id: str) -> TenantDetail | None:
        tenant = await self._ps.get_tenant(tenant_id)
        if not tenant:
            return None
        leases = await self._ps.list_leases(tenant_id=tenant_id)
        lease_info: list[LeaseInfo] = []
        for le in leases:
            unit = await self._ps.get_unit(le.unit_id)
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
        return TenantDetail(
            tenant_id=tenant_id,
            name=tenant.name,
            email=tenant.email,
            phone=tenant.phone,
            leases=lease_info,
        )
