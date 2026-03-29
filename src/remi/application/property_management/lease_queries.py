"""LeaseQueryService — lease expiration queries.

Pure PropertyStore read-model.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel

from remi.domain.properties.enums import LeaseStatus
from remi.domain.properties.ports import PropertyStore


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ExpiringLeaseItem(BaseModel):
    lease_id: str
    tenant: str
    unit: str
    property: str
    monthly_rent: float
    end_date: str
    days_left: int


class ExpiringLeasesResult(BaseModel):
    days_window: int
    count: int
    leases: list[ExpiringLeaseItem]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LeaseQueryService:
    """Lease expiration read models."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

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
            items.append(ExpiringLeaseItem(
                lease_id=le.id,
                tenant=tenant.name if tenant else le.tenant_id,
                unit=unit.unit_number if unit else le.unit_id,
                property=prop.name if prop else le.property_id,
                monthly_rent=float(le.monthly_rent),
                end_date=le.end_date.isoformat(),
                days_left=(le.end_date - today).days,
            ))

        return ExpiringLeasesResult(
            days_window=days,
            count=len(items),
            leases=items,
        )
