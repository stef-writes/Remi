"""Leases — list and expiring-lease queries."""

from __future__ import annotations

from datetime import date, timedelta

from remi.application.core.models import LeaseStatus
from remi.application.core.protocols import PropertyStore

from ._models import (
    ExpiringLeaseItem,
    ExpiringLeasesResult,
    LeaseListItem,
    LeaseListResult,
)


class LeaseResolver:
    """Entity resolver for leases."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_leases(
        self,
        property_id: str | None = None,
        status: str | None = None,
    ) -> LeaseListResult:
        lease_status = LeaseStatus(status) if status else None
        leases = await self._ps.list_leases(property_id=property_id, status=lease_status)
        items: list[LeaseListItem] = []
        for le in leases:
            tenant = await self._ps.get_tenant(le.tenant_id)
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
        return LeaseListResult(count=len(items), leases=items)

    async def expiring_leases(self, days: int = 60) -> ExpiringLeasesResult:
        today = date.today()
        deadline = today + timedelta(days=days)

        leases = await self._ps.list_leases(status=LeaseStatus.ACTIVE)
        expiring = [le for le in leases if le.end_date <= deadline]
        expiring.sort(key=lambda le: le.end_date)

        items: list[ExpiringLeaseItem] = []
        for le in expiring:
            tenant = await self._ps.get_tenant(le.tenant_id)
            unit = await self._ps.get_unit(le.unit_id)
            prop = await self._ps.get_property(le.property_id)
            items.append(
                ExpiringLeaseItem(
                    lease_id=le.id,
                    tenant=tenant.name if tenant else le.tenant_id,
                    unit=unit.unit_number if unit else le.unit_id,
                    property=prop.name if prop else le.property_id,
                    monthly_rent=float(le.monthly_rent),
                    end_date=le.end_date.isoformat(),
                    days_left=(le.end_date - today).days,
                )
            )

        return ExpiringLeasesResult(days_window=days, count=len(items), leases=items)
