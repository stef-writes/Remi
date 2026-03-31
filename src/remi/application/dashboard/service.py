"""DashboardQueryService — five typed dashboard views over PropertyStore.

Zero LLM imports. Zero document store imports. Pure aggregation.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel

from remi.domain.properties.enums import LeaseStatus, OccupancyStatus, UnitStatus

if TYPE_CHECKING:
    from remi.domain.properties.ports import PropertyStore

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ManagerOverview(BaseModel):
    manager_id: str
    manager_name: str
    portfolio_count: int
    property_count: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_monthly_rent: float
    total_market_rent: float
    loss_to_lease: float


class PortfolioOverview(BaseModel):
    total_managers: int
    total_portfolios: int
    total_properties: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_monthly_rent: float
    total_market_rent: float
    total_loss_to_lease: float
    managers: list[ManagerOverview]


class DelinquentTenant(BaseModel):
    tenant_id: str
    tenant_name: str
    status: str
    property_name: str
    unit_number: str
    balance_owed: float
    balance_0_30: float
    balance_30_plus: float
    last_payment_date: str | None
    tags: list[str]


class DelinquencyBoard(BaseModel):
    total_delinquent: int
    total_balance: float
    tenants: list[DelinquentTenant]


class ExpiringLease(BaseModel):
    lease_id: str
    tenant_name: str
    property_name: str
    unit_number: str
    monthly_rent: float
    market_rent: float
    end_date: str
    days_left: int
    is_month_to_month: bool


class LeaseCalendar(BaseModel):
    days_window: int
    total_expiring: int
    month_to_month_count: int
    leases: list[ExpiringLease]


class RentRollUnit(BaseModel):
    unit_id: str
    unit_number: str
    occupancy_status: str | None
    bedrooms: int | None
    bathrooms: float | None
    sqft: int | None
    current_rent: float
    market_rent: float
    rent_gap: float
    tenant_name: str | None
    lease_end: str | None
    days_to_expiry: int | None


class RentRollView(BaseModel):
    property_id: str
    property_name: str
    total_units: int
    occupied: int
    vacant: int
    total_monthly_rent: float
    total_market_rent: float
    loss_to_lease: float
    units: list[RentRollUnit]


class VacantUnit(BaseModel):
    unit_id: str
    unit_number: str
    property_id: str
    property_name: str
    occupancy_status: str | None
    days_vacant: int | None
    market_rent: float
    listed_on_website: bool
    listed_on_internet: bool


class VacancyTracker(BaseModel):
    total_vacant: int
    total_notice: int
    total_market_rent_at_risk: float
    avg_days_vacant: float | None
    units: list[VacantUnit]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DashboardQueryService:
    """Pure PropertyStore aggregation — no LLM, no document store."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def portfolio_overview(
        self, manager_id: str | None = None
    ) -> PortfolioOverview:
        if manager_id:
            managers_list = []
            mgr = await self._ps.get_manager(manager_id)
            if mgr:
                managers_list = [mgr]
        else:
            managers_list = await self._ps.list_managers()

        mgr_overviews: list[ManagerOverview] = []
        grand_units = 0
        grand_occ = 0
        grand_vac = 0
        grand_rent = Decimal("0")
        grand_market = Decimal("0")
        grand_ltl = Decimal("0")
        grand_portfolios = 0
        grand_properties = 0

        for mgr in managers_list:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            m_units = 0
            m_occ = 0
            m_vac = 0
            m_rent = Decimal("0")
            m_market = Decimal("0")
            m_ltl = Decimal("0")
            m_props = 0

            for pf in portfolios:
                props = await self._ps.list_properties(portfolio_id=pf.id)
                m_props += len(props)
                for prop in props:
                    units = await self._ps.list_units(property_id=prop.id)
                    for u in units:
                        m_units += 1
                        if u.status == UnitStatus.OCCUPIED or (
                            u.occupancy_status and u.occupancy_status == OccupancyStatus.OCCUPIED
                        ):
                            m_occ += 1
                        elif u.status == UnitStatus.VACANT or (
                            u.occupancy_status and u.occupancy_status in (
                                OccupancyStatus.VACANT_RENTED, OccupancyStatus.VACANT_UNRENTED
                            )
                        ):
                            m_vac += 1
                        m_rent += u.current_rent
                        m_market += u.market_rent
                        if u.current_rent < u.market_rent:
                            m_ltl += u.market_rent - u.current_rent

            grand_portfolios += len(portfolios)
            grand_properties += m_props
            grand_units += m_units
            grand_occ += m_occ
            grand_vac += m_vac
            grand_rent += m_rent
            grand_market += m_market
            grand_ltl += m_ltl

            mgr_overviews.append(ManagerOverview(
                manager_id=mgr.id,
                manager_name=mgr.name,
                portfolio_count=len(portfolios),
                property_count=m_props,
                total_units=m_units,
                occupied=m_occ,
                vacant=m_vac,
                occupancy_rate=round(m_occ / m_units, 3) if m_units else 0,
                total_monthly_rent=float(m_rent),
                total_market_rent=float(m_market),
                loss_to_lease=float(m_ltl),
            ))

        return PortfolioOverview(
            total_managers=len(managers_list),
            total_portfolios=grand_portfolios,
            total_properties=grand_properties,
            total_units=grand_units,
            occupied=grand_occ,
            vacant=grand_vac,
            occupancy_rate=round(grand_occ / grand_units, 3) if grand_units else 0,
            total_monthly_rent=float(grand_rent),
            total_market_rent=float(grand_market),
            total_loss_to_lease=float(grand_ltl),
            managers=mgr_overviews,
        )

    async def delinquency_board(
        self, manager_id: str | None = None
    ) -> DelinquencyBoard:
        tenants = await self._ps.list_tenants()

        # Pre-resolve each tenant's primary lease → property + unit
        tenant_context: dict[str, tuple[str, str]] = {}
        if manager_id:
            allowed_property_ids = await self._property_ids_for_manager(manager_id)
            filtered = []
            for t in tenants:
                leases = await self._ps.list_leases(tenant_id=t.id)
                if any(le.property_id in allowed_property_ids for le in leases):
                    filtered.append(t)
                if leases:
                    le = leases[0]
                    prop = await self._ps.get_property(le.property_id)
                    unit = await self._ps.get_unit(le.unit_id)
                    tenant_context[t.id] = (
                        prop.name if prop else le.property_id,
                        unit.unit_number if unit else le.unit_id,
                    )
            tenants = filtered
        else:
            for t in tenants:
                leases = await self._ps.list_leases(tenant_id=t.id)
                if leases:
                    le = leases[0]
                    prop = await self._ps.get_property(le.property_id)
                    unit = await self._ps.get_unit(le.unit_id)
                    tenant_context[t.id] = (
                        prop.name if prop else le.property_id,
                        unit.unit_number if unit else le.unit_id,
                    )

        delinquent = [t for t in tenants if t.balance_owed > 0]
        delinquent.sort(key=lambda t: t.balance_owed, reverse=True)

        return DelinquencyBoard(
            total_delinquent=len(delinquent),
            total_balance=float(sum(t.balance_owed for t in delinquent)),
            tenants=[
                DelinquentTenant(
                    tenant_id=t.id,
                    tenant_name=t.name,
                    status=t.status.value,
                    property_name=tenant_context.get(t.id, ("", ""))[0],
                    unit_number=tenant_context.get(t.id, ("", ""))[1],
                    balance_owed=float(t.balance_owed),
                    balance_0_30=float(t.balance_0_30),
                    balance_30_plus=float(t.balance_30_plus),
                    last_payment_date=t.last_payment_date.isoformat() if t.last_payment_date else None,
                    tags=t.tags,
                )
                for t in delinquent
            ],
        )

    async def lease_expiration_calendar(
        self, days: int = 90, manager_id: str | None = None
    ) -> LeaseCalendar:
        today = date.today()
        deadline = today + timedelta(days=days)
        leases = await self._ps.list_leases(status=LeaseStatus.ACTIVE)

        if manager_id:
            allowed = await self._property_ids_for_manager(manager_id)
            leases = [le for le in leases if le.property_id in allowed]

        expiring = [le for le in leases if le.end_date <= deadline or le.is_month_to_month]
        expiring.sort(key=lambda le: le.end_date)

        items: list[ExpiringLease] = []
        mtm_count = 0
        for le in expiring:
            tenant = await self._ps.get_tenant(le.tenant_id)
            prop = await self._ps.get_property(le.property_id)
            unit = await self._ps.get_unit(le.unit_id)
            if le.is_month_to_month:
                mtm_count += 1
            items.append(ExpiringLease(
                lease_id=le.id,
                tenant_name=tenant.name if tenant else le.tenant_id,
                property_name=prop.name if prop else le.property_id,
                unit_number=unit.unit_number if unit else le.unit_id,
                monthly_rent=float(le.monthly_rent),
                market_rent=float(le.market_rent),
                end_date=le.end_date.isoformat(),
                days_left=(le.end_date - today).days,
                is_month_to_month=le.is_month_to_month,
            ))

        return LeaseCalendar(
            days_window=days,
            total_expiring=len(items),
            month_to_month_count=mtm_count,
            leases=items,
        )

    async def rent_roll(self, property_id: str) -> RentRollView | None:
        prop = await self._ps.get_property(property_id)
        if not prop:
            return None

        units = await self._ps.list_units(property_id=property_id)
        all_leases = await self._ps.list_leases(property_id=property_id)
        today = date.today()

        total_rent = Decimal("0")
        total_market = Decimal("0")
        total_ltl = Decimal("0")
        occ = 0
        vac = 0
        rows: list[RentRollUnit] = []

        for u in units:
            is_occ = u.status == UnitStatus.OCCUPIED or (
                u.occupancy_status and u.occupancy_status == OccupancyStatus.OCCUPIED
            )
            if is_occ:
                occ += 1
            else:
                vac += 1

            total_rent += u.current_rent
            total_market += u.market_rent
            if u.current_rent < u.market_rent:
                total_ltl += u.market_rent - u.current_rent

            unit_leases = [le for le in all_leases if le.unit_id == u.id and le.status == LeaseStatus.ACTIVE]
            current_lease = unit_leases[0] if unit_leases else None
            tenant_name: str | None = None
            if current_lease:
                tenant = await self._ps.get_tenant(current_lease.tenant_id)
                tenant_name = tenant.name if tenant else None

            days_to_expiry: int | None = None
            lease_end: str | None = None
            if current_lease:
                days_to_expiry = (current_lease.end_date - today).days
                lease_end = current_lease.end_date.isoformat()

            rows.append(RentRollUnit(
                unit_id=u.id,
                unit_number=u.unit_number,
                occupancy_status=u.occupancy_status.value if u.occupancy_status else None,
                bedrooms=u.bedrooms,
                bathrooms=u.bathrooms,
                sqft=u.sqft,
                current_rent=float(u.current_rent),
                market_rent=float(u.market_rent),
                rent_gap=float(u.current_rent - u.market_rent),
                tenant_name=tenant_name,
                lease_end=lease_end,
                days_to_expiry=days_to_expiry,
            ))

        return RentRollView(
            property_id=property_id,
            property_name=prop.name,
            total_units=len(units),
            occupied=occ,
            vacant=vac,
            total_monthly_rent=float(total_rent),
            total_market_rent=float(total_market),
            loss_to_lease=float(total_ltl),
            units=rows,
        )

    async def vacancy_tracker(
        self, manager_id: str | None = None
    ) -> VacancyTracker:
        all_units = await self._ps.list_units()

        if manager_id:
            allowed = await self._property_ids_for_manager(manager_id)
            all_units = [u for u in all_units if u.property_id in allowed]

        vacant_units: list[VacantUnit] = []
        notice_count = 0
        total_risk = Decimal("0")
        days_list: list[int] = []

        for u in all_units:
            is_vacant = u.occupancy_status in (
                OccupancyStatus.VACANT_RENTED, OccupancyStatus.VACANT_UNRENTED
            ) if u.occupancy_status else u.status == UnitStatus.VACANT

            is_notice = u.occupancy_status in (
                OccupancyStatus.NOTICE_RENTED, OccupancyStatus.NOTICE_UNRENTED
            ) if u.occupancy_status else False

            if not (is_vacant or is_notice):
                continue

            if is_notice:
                notice_count += 1

            prop = await self._ps.get_property(u.property_id)
            total_risk += u.market_rent
            if u.days_vacant is not None:
                days_list.append(u.days_vacant)

            vacant_units.append(VacantUnit(
                unit_id=u.id,
                unit_number=u.unit_number,
                property_id=u.property_id,
                property_name=prop.name if prop else u.property_id,
                occupancy_status=u.occupancy_status.value if u.occupancy_status else "vacant",
                days_vacant=u.days_vacant,
                market_rent=float(u.market_rent),
                listed_on_website=u.listed_on_website,
                listed_on_internet=u.listed_on_internet,
            ))

        vacant_units.sort(key=lambda v: v.days_vacant or 0, reverse=True)

        return VacancyTracker(
            total_vacant=len([v for v in vacant_units if v.occupancy_status not in ("notice_rented", "notice_unrented")]),
            total_notice=notice_count,
            total_market_rent_at_risk=float(total_risk),
            avg_days_vacant=round(sum(days_list) / len(days_list), 1) if days_list else None,
            units=vacant_units,
        )

    # -- Internal helpers --

    async def _property_ids_for_manager(self, manager_id: str) -> set[str]:
        portfolios = await self._ps.list_portfolios(manager_id=manager_id)
        ids: set[str] = set()
        for pf in portfolios:
            props = await self._ps.list_properties(portfolio_id=pf.id)
            ids.update(p.id for p in props)
        return ids
