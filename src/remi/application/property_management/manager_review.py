"""ManagerReviewService — director-level portfolio aggregation.

Pure PropertyStore read-model: no LLM, no document store.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel

from remi.domain.properties.enums import LeaseStatus, MaintenanceStatus, UnitStatus

if TYPE_CHECKING:
    from remi.domain.properties.ports import PropertyStore

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PropertySummary(BaseModel):
    property_id: str
    property_name: str
    portfolio_id: str
    portfolio_name: str
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    monthly_actual: float
    monthly_market: float
    loss_to_lease: float
    vacancy_loss: float
    open_maintenance: int
    emergency_maintenance: int
    expiring_leases: int
    expired_leases: int
    below_market_units: int
    issue_count: int


class UnitIssue(BaseModel):
    property_id: str
    property_name: str
    unit_id: str
    unit_number: str
    issues: list[str]
    monthly_impact: float


class ManagerSummary(BaseModel):
    manager_id: str
    name: str
    email: str
    company: str | None
    portfolio_count: int
    property_count: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_market_rent: float
    total_actual_rent: float
    total_loss_to_lease: float
    total_vacancy_loss: float
    open_maintenance: int
    emergency_maintenance: int
    expiring_leases_90d: int
    expired_leases: int
    below_market_units: int
    properties: list[PropertySummary]
    top_issues: list[UnitIssue]


_BELOW_MARKET_THRESHOLD = 0.03


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ManagerReviewService:
    """Director-level portfolio roll-up over PropertyStore."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def aggregate_manager(self, manager_id: str) -> ManagerSummary | None:
        manager = await self._ps.get_manager(manager_id)
        if not manager:
            return None

        portfolios = await self._ps.list_portfolios(manager_id=manager_id)
        today = date.today()

        total_units = 0
        occupied = 0
        vacant = 0
        total_market = Decimal("0")
        total_actual = Decimal("0")
        total_loss_to_lease = Decimal("0")
        total_vacancy_loss = Decimal("0")
        open_maintenance = 0
        emergency_maintenance = 0
        expiring_leases_90d = 0
        expired_leases = 0
        below_market_units = 0
        property_count = 0

        property_summaries: list[PropertySummary] = []
        top_issues: list[UnitIssue] = []

        for portfolio in portfolios:
            properties = await self._ps.list_properties(portfolio_id=portfolio.id)

            for prop in properties:
                property_count += 1
                units = await self._ps.list_units(property_id=prop.id)
                leases = await self._ps.list_leases(property_id=prop.id)
                maint = await self._ps.list_maintenance_requests(property_id=prop.id)

                p_units = len(units)
                p_occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
                p_vac = sum(1 for u in units if u.status == UnitStatus.VACANT)
                p_market = sum((u.market_rent for u in units), Decimal("0"))
                p_actual = sum((u.current_rent for u in units), Decimal("0"))
                p_ltl = sum(
                    (u.market_rent - u.current_rent for u in units if u.current_rent < u.market_rent),
                    Decimal("0"),
                )
                p_vloss = sum(
                    (u.market_rent for u in units if u.status == UnitStatus.VACANT),
                    Decimal("0"),
                )
                p_open_maint = sum(
                    1 for m in maint
                    if m.status in (MaintenanceStatus.OPEN, MaintenanceStatus.IN_PROGRESS)
                )
                p_emergency = sum(
                    1 for m in maint
                    if m.status in (MaintenanceStatus.OPEN, MaintenanceStatus.IN_PROGRESS)
                    and m.priority.value == "emergency"
                )

                p_expiring = 0
                p_expired = 0
                for le in leases:
                    if le.status == LeaseStatus.ACTIVE:
                        days_left = (le.end_date - today).days
                        if 0 < days_left <= 90:
                            p_expiring += 1
                    elif le.status == LeaseStatus.EXPIRED:
                        p_expired += 1

                p_below = sum(
                    1 for u in units
                    if u.market_rent > 0 and u.current_rent < u.market_rent
                    and float((u.market_rent - u.current_rent) / u.market_rent) > _BELOW_MARKET_THRESHOLD
                )

                total_units += p_units
                occupied += p_occ
                vacant += p_vac
                total_market += p_market
                total_actual += p_actual
                total_loss_to_lease += p_ltl
                total_vacancy_loss += p_vloss
                open_maintenance += p_open_maint
                emergency_maintenance += p_emergency
                expiring_leases_90d += p_expiring
                expired_leases += p_expired
                below_market_units += p_below

                issue_count = p_vac + p_open_maint + p_expiring + p_expired + p_below
                property_summaries.append(PropertySummary(
                    property_id=prop.id,
                    property_name=prop.name,
                    portfolio_id=portfolio.id,
                    portfolio_name=portfolio.name,
                    total_units=p_units,
                    occupied=p_occ,
                    vacant=p_vac,
                    occupancy_rate=round(p_occ / p_units, 3) if p_units else 0,
                    monthly_actual=float(p_actual),
                    monthly_market=float(p_market),
                    loss_to_lease=float(p_ltl),
                    vacancy_loss=float(p_vloss),
                    open_maintenance=p_open_maint,
                    emergency_maintenance=p_emergency,
                    expiring_leases=p_expiring,
                    expired_leases=p_expired,
                    below_market_units=p_below,
                    issue_count=issue_count,
                ))

                for u in units:
                    unit_issues: list[str] = []
                    if u.status == UnitStatus.VACANT:
                        unit_issues.append("vacant")
                    if (
                        u.market_rent > 0
                        and u.current_rent < u.market_rent
                        and float((u.market_rent - u.current_rent) / u.market_rent) > _BELOW_MARKET_THRESHOLD
                    ):
                        unit_issues.append("below_market")

                    unit_leases = [le for le in leases if le.unit_id == u.id]
                    active = next((le for le in unit_leases if le.status == LeaseStatus.ACTIVE), None)
                    if active and 0 < (active.end_date - today).days <= 90:
                        unit_issues.append("expiring_soon")
                    exp = next((le for le in unit_leases if le.status == LeaseStatus.EXPIRED), None)
                    if exp:
                        unit_issues.append("expired_lease")

                    unit_maint = [
                        m for m in maint
                        if m.unit_id == u.id
                        and m.status in (MaintenanceStatus.OPEN, MaintenanceStatus.IN_PROGRESS)
                    ]
                    if unit_maint:
                        unit_issues.append("open_maintenance")

                    if unit_issues:
                        top_issues.append(UnitIssue(
                            property_id=prop.id,
                            property_name=prop.name,
                            unit_id=u.id,
                            unit_number=u.unit_number,
                            issues=unit_issues,
                            monthly_impact=float(u.market_rent - u.current_rent) if u.current_rent < u.market_rent else 0,
                        ))

        property_summaries.sort(key=lambda p: p.issue_count, reverse=True)
        top_issues.sort(key=lambda i: len(i.issues), reverse=True)

        return ManagerSummary(
            manager_id=manager.id,
            name=manager.name,
            email=manager.email,
            company=manager.company,
            portfolio_count=len(portfolios),
            property_count=property_count,
            total_units=total_units,
            occupied=occupied,
            vacant=vacant,
            occupancy_rate=round(occupied / total_units, 3) if total_units else 0,
            total_market_rent=float(total_market),
            total_actual_rent=float(total_actual),
            total_loss_to_lease=float(total_loss_to_lease),
            total_vacancy_loss=float(total_vacancy_loss),
            open_maintenance=open_maintenance,
            emergency_maintenance=emergency_maintenance,
            expiring_leases_90d=expiring_leases_90d,
            expired_leases=expired_leases,
            below_market_units=below_market_units,
            properties=property_summaries,
            top_issues=top_issues[:50],
        )

    async def list_manager_summaries(self) -> list[ManagerSummary]:
        managers = await self._ps.list_managers()
        results: list[ManagerSummary] = []
        for m in managers:
            summary = await self.aggregate_manager(m.id)
            if summary:
                results.append(summary)
        return results
