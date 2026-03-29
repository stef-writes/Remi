"""RentRollService — detailed rent-roll assembly for a property.

Pure PropertyStore aggregation: units, leases, tenants, maintenance joined
into a prioritised issue-tagged view.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from remi.domain.properties.enums import LeaseStatus, MaintenanceStatus, UnitStatus
from remi.domain.properties.ports import PropertyStore


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class LeaseInRentRoll(BaseModel):
    id: str
    status: str
    start_date: str
    end_date: str
    monthly_rent: float
    deposit: float
    days_to_expiry: int | None


class TenantInRentRoll(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None


class MaintenanceInRentRoll(BaseModel):
    id: str
    title: str
    category: str
    priority: str
    status: str
    cost: float | None


class RentRollRow(BaseModel):
    unit_id: str
    unit_number: str
    floor: int | None
    bedrooms: int | None
    bathrooms: float | None
    sqft: int | None
    status: str
    market_rent: float
    current_rent: float
    rent_gap: float
    pct_below_market: float
    lease: LeaseInRentRoll | None
    tenant: TenantInRentRoll | None
    open_maintenance: int
    maintenance_items: list[MaintenanceInRentRoll]
    issues: list[str]


class RentRollResult(BaseModel):
    property_id: str
    property_name: str
    total_units: int
    occupied: int
    vacant: int
    total_market_rent: float
    total_actual_rent: float
    total_loss_to_lease: float
    total_vacancy_loss: float
    rows: list[RentRollRow]


_BELOW_MARKET_THRESHOLD = 3.0  # percent


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RentRollService:
    """Builds a detailed rent-roll view for a property."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def build_rent_roll(self, property_id: str) -> RentRollResult | None:
        prop = await self._ps.get_property(property_id)
        if not prop:
            return None

        units = await self._ps.list_units(property_id=property_id)
        all_leases = await self._ps.list_leases(property_id=property_id)
        all_maintenance = await self._ps.list_maintenance_requests(property_id=property_id)

        tenant_cache: dict[str, Any] = {}
        today = date.today()
        rows: list[RentRollRow] = []
        total_market = Decimal("0")
        total_actual = Decimal("0")
        total_loss_to_lease = Decimal("0")
        total_vacancy_loss = Decimal("0")

        for unit in units:
            unit_leases = [le for le in all_leases if le.unit_id == unit.id]
            active_lease = next(
                (le for le in unit_leases if le.status == LeaseStatus.ACTIVE), None
            )
            expired_lease = next(
                (le for le in unit_leases if le.status == LeaseStatus.EXPIRED), None
            )
            current_lease = active_lease or expired_lease

            tenant = None
            if current_lease:
                tid = current_lease.tenant_id
                if tid not in tenant_cache:
                    tenant_cache[tid] = await self._ps.get_tenant(tid)
                tenant = tenant_cache[tid]

            open_maint = [
                mr for mr in all_maintenance
                if mr.unit_id == unit.id
                and mr.status in (MaintenanceStatus.OPEN, MaintenanceStatus.IN_PROGRESS)
            ]

            rent_gap = float(unit.current_rent - unit.market_rent)
            pct_below = (
                round(float((unit.market_rent - unit.current_rent) / unit.market_rent) * 100, 1)
                if unit.market_rent > 0 and unit.current_rent < unit.market_rent
                else 0.0
            )

            days_to_expiry: int | None = None
            if current_lease:
                days_to_expiry = (current_lease.end_date - today).days

            issues: list[str] = []
            if unit.status == UnitStatus.VACANT:
                issues.append("vacant")
            if unit.status == UnitStatus.MAINTENANCE:
                issues.append("down_for_maintenance")
            if pct_below > _BELOW_MARKET_THRESHOLD:
                issues.append("below_market")
            if current_lease and current_lease.status == LeaseStatus.EXPIRED:
                issues.append("expired_lease")
            if days_to_expiry is not None and 0 < days_to_expiry <= 90:
                issues.append("expiring_soon")
            if len(open_maint) > 0:
                issues.append("open_maintenance")

            total_market += unit.market_rent
            total_actual += unit.current_rent
            if unit.current_rent < unit.market_rent:
                total_loss_to_lease += unit.market_rent - unit.current_rent
            if unit.status == UnitStatus.VACANT:
                total_vacancy_loss += unit.market_rent

            rows.append(RentRollRow(
                unit_id=unit.id,
                unit_number=unit.unit_number,
                floor=unit.floor,
                bedrooms=unit.bedrooms,
                bathrooms=unit.bathrooms,
                sqft=unit.sqft,
                status=unit.status.value,
                market_rent=float(unit.market_rent),
                current_rent=float(unit.current_rent),
                rent_gap=rent_gap,
                pct_below_market=pct_below,
                lease=LeaseInRentRoll(
                    id=current_lease.id,
                    status=current_lease.status.value,
                    start_date=current_lease.start_date.isoformat(),
                    end_date=current_lease.end_date.isoformat(),
                    monthly_rent=float(current_lease.monthly_rent),
                    deposit=float(current_lease.deposit),
                    days_to_expiry=days_to_expiry,
                ) if current_lease else None,
                tenant=TenantInRentRoll(
                    id=tenant.id,
                    name=tenant.name,
                    email=tenant.email,
                    phone=tenant.phone,
                ) if tenant else None,
                open_maintenance=len(open_maint),
                maintenance_items=[
                    MaintenanceInRentRoll(
                        id=mr.id,
                        title=mr.title,
                        category=mr.category.value,
                        priority=mr.priority.value,
                        status=mr.status.value,
                        cost=float(mr.cost) if mr.cost else None,
                    )
                    for mr in open_maint
                ],
                issues=issues,
            ))

        rows.sort(key=lambda r: len(r.issues), reverse=True)

        return RentRollResult(
            property_id=property_id,
            property_name=prop.name,
            total_units=len(units),
            occupied=sum(1 for u in units if u.status == UnitStatus.OCCUPIED),
            vacant=sum(1 for u in units if u.status == UnitStatus.VACANT),
            total_market_rent=float(total_market),
            total_actual_rent=float(total_actual),
            total_loss_to_lease=float(total_loss_to_lease),
            total_vacancy_loss=float(total_vacancy_loss),
            rows=rows,
        )
