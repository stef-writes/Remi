"""PortfolioQueryService — unified entity list/detail/summary projections."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from remi.application.core.models import LeaseStatus, MaintenanceStatus, UnitStatus
from remi.application.core.protocols import PropertyStore

from ._models import (
    ExpiringLeaseItem,
    ExpiringLeasesResult,
    LeaseListItem,
    LeaseListResult,
    MaintenanceItem,
    MaintenanceListResult,
    MaintenanceSummaryResult,
    PortfolioListItem,
    PortfolioSummaryResult,
    PropertyDetail,
    PropertyDetailUnit,
    PropertyInPortfolio,
    PropertyListItem,
    UnitListItem,
    UnitListResult,
)


class PortfolioQueryService:
    """Unified read-model projections for all portfolio entities."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    # -- Portfolios ----------------------------------------------------------

    async def list_portfolios(self, manager_id: str | None = None) -> list[PortfolioListItem]:
        portfolios = await self._ps.list_portfolios(manager_id=manager_id)
        items: list[PortfolioListItem] = []
        for p in portfolios:
            manager = await self._ps.get_manager(p.manager_id)
            props = await self._ps.list_properties(portfolio_id=p.id)
            items.append(
                PortfolioListItem(
                    id=p.id,
                    name=p.name,
                    manager=manager.name if manager else "Unknown",
                    property_count=len(props),
                    description=p.description,
                )
            )
        return items

    async def portfolio_summary(self, portfolio_id: str) -> PortfolioSummaryResult | None:
        portfolio = await self._ps.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        manager = await self._ps.get_manager(portfolio.manager_id)
        properties = await self._ps.list_properties(portfolio_id=portfolio_id)

        total_units = 0
        occupied = 0
        total_revenue = Decimal("0")
        prop_details: list[PropertyInPortfolio] = []

        for prop in properties:
            units = await self._ps.list_units(property_id=prop.id)
            occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
            rev = sum((u.current_rent for u in units), Decimal("0"))
            total_units += len(units)
            occupied += occ
            total_revenue += rev
            prop_details.append(
                PropertyInPortfolio(
                    id=prop.id,
                    name=prop.name,
                    type=prop.property_type.value,
                    units=len(units),
                    occupied=occ,
                    monthly_revenue=float(rev),
                )
            )

        return PortfolioSummaryResult(
            portfolio_id=portfolio_id,
            name=portfolio.name,
            manager=manager.name if manager else "Unknown",
            total_properties=len(properties),
            total_units=total_units,
            occupied_units=occupied,
            occupancy_rate=round(occupied / total_units, 3) if total_units else 0,
            monthly_revenue=float(total_revenue),
            properties=prop_details,
        )

    # -- Properties ----------------------------------------------------------

    async def list_properties(self, portfolio_id: str | None = None) -> list[PropertyListItem]:
        properties = await self._ps.list_properties(portfolio_id=portfolio_id)
        items: list[PropertyListItem] = []
        for p in properties:
            units = await self._ps.list_units(property_id=p.id)
            occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
            items.append(
                PropertyListItem(
                    id=p.id,
                    name=p.name,
                    address=p.address.one_line(),
                    type=p.property_type.value,
                    year_built=p.year_built,
                    total_units=len(units),
                    occupied=occ,
                )
            )
        return items

    async def get_property_detail(self, property_id: str) -> PropertyDetail | None:
        prop = await self._ps.get_property(property_id)
        if not prop:
            return None

        units = await self._ps.list_units(property_id=property_id)
        active_leases = await self._ps.list_leases(
            property_id=property_id, status=LeaseStatus.ACTIVE
        )
        occupied = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
        vacant = sum(1 for u in units if u.status == UnitStatus.VACANT)
        revenue = sum((u.current_rent for u in units), Decimal("0"))

        return PropertyDetail(
            id=property_id,
            name=prop.name,
            address=prop.address,
            property_type=prop.property_type.value,
            year_built=prop.year_built,
            total_units=len(units),
            occupied=occupied,
            vacant=vacant,
            occupancy_rate=round(occupied / len(units), 3) if units else 0,
            monthly_revenue=float(revenue),
            active_leases=len(active_leases),
            units=[
                PropertyDetailUnit(
                    id=u.id,
                    property_id=property_id,
                    unit_number=u.unit_number,
                    status=u.status.value,
                    occupancy_status=u.occupancy_status.value if u.occupancy_status else None,
                    bedrooms=u.bedrooms,
                    bathrooms=u.bathrooms,
                    sqft=u.sqft,
                    floor=u.floor,
                    market_rent=float(u.market_rent),
                    current_rent=float(u.current_rent),
                )
                for u in units
            ],
        )

    # -- Leases --------------------------------------------------------------

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

    # -- Maintenance ---------------------------------------------------------

    async def list_maintenance(
        self,
        property_id: str | None = None,
        status: str | None = None,
    ) -> MaintenanceListResult:
        maint_status = MaintenanceStatus(status) if status else None
        requests = await self._ps.list_maintenance_requests(
            property_id=property_id, status=maint_status
        )
        requests.sort(key=lambda r: r.created_at, reverse=True)

        return MaintenanceListResult(
            count=len(requests),
            requests=[
                MaintenanceItem(
                    id=r.id,
                    property_id=r.property_id,
                    unit_id=r.unit_id,
                    title=r.title,
                    category=r.category.value,
                    priority=r.priority.value,
                    status=r.status.value,
                    cost=float(r.cost) if r.cost else None,
                    created=r.created_at.isoformat(),
                    resolved=r.resolved_at.isoformat() if r.resolved_at else None,
                )
                for r in requests
            ],
        )

    # -- Leases (full list) ---------------------------------------------------

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

    # -- Units (cross-property) -----------------------------------------------

    async def list_units(
        self,
        property_id: str | None = None,
        status: str | None = None,
    ) -> UnitListResult:
        unit_status = UnitStatus(status) if status else None
        units = await self._ps.list_units(property_id=property_id, status=unit_status)
        items: list[UnitListItem] = []
        for u in units:
            prop = await self._ps.get_property(u.property_id)
            items.append(
                UnitListItem(
                    id=u.id,
                    unit_number=u.unit_number,
                    property_name=prop.name if prop else u.property_id,
                    property_id=u.property_id,
                    status=u.status.value,
                    bedrooms=u.bedrooms,
                    sqft=u.sqft,
                    market_rent=float(u.market_rent),
                    current_rent=float(u.current_rent),
                )
            )
        return UnitListResult(count=len(items), units=items)

    # -- Maintenance summary --------------------------------------------------

    async def maintenance_summary(
        self, property_id: str | None = None
    ) -> MaintenanceSummaryResult:
        requests = await self._ps.list_maintenance_requests(property_id=property_id)

        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        total_cost = Decimal("0")

        for r in requests:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
            by_category[r.category.value] = by_category.get(r.category.value, 0) + 1
            if r.cost:
                total_cost += r.cost

        return MaintenanceSummaryResult(
            total=len(requests),
            by_status=by_status,
            by_category=by_category,
            total_cost=float(total_cost),
        )
