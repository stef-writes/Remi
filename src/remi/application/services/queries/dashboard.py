"""DashboardQueryService — five typed dashboard views over PropertyStore.

Zero LLM imports. Zero document store imports. Pure aggregation.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from remi.agent.graph.stores import KnowledgeStore
from remi.application.core.models import (
    LeaseStatus,
    OccupancyStatus,
    UnitStatus,
)
from remi.application.core.protocols import PropertyStore
from remi.application.core.rules import is_occupied, is_vacant, loss_to_lease

from ._models import (
    DelinquencyBoard,
    DelinquentTenant,
    ExpiringLease,
    LeaseCalendar,
    ManagerOverview,
    PortfolioOverview,
    RentRollUnit,
    RentRollView,
    VacancyTracker,
    VacantUnit,
)


class DashboardQueryService:
    """Pure PropertyStore aggregation — no LLM, no document store."""

    def __init__(
        self,
        property_store: PropertyStore,
        knowledge_store: KnowledgeStore | None = None,
    ) -> None:
        self._ps = property_store
        self._ks = knowledge_store

    async def portfolio_overview(self, manager_id: str | None = None) -> PortfolioOverview:
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

        all_mgr_portfolios = await asyncio.gather(
            *[self._ps.list_portfolios(manager_id=mgr.id) for mgr in managers_list]
        )

        for mgr, portfolios in zip(managers_list, all_mgr_portfolios, strict=True):
            pf_props = await asyncio.gather(
                *[self._ps.list_properties(portfolio_id=pf.id) for pf in portfolios]
            )
            all_props = [prop for props in pf_props for prop in props]

            all_unit_lists = await asyncio.gather(
                *[self._ps.list_units(property_id=prop.id) for prop in all_props]
            )

            m_units = 0
            m_occ = 0
            m_vac = 0
            m_rent = Decimal("0")
            m_market = Decimal("0")
            m_ltl = Decimal("0")

            for unit_list in all_unit_lists:
                for u in unit_list:
                    m_units += 1
                    if is_occupied(u):
                        m_occ += 1
                    elif is_vacant(u):
                        m_vac += 1
                    m_rent += u.current_rent
                    m_market += u.market_rent
                    m_ltl += loss_to_lease(u)

            grand_portfolios += len(portfolios)
            grand_properties += len(all_props)
            grand_units += m_units
            grand_occ += m_occ
            grand_vac += m_vac
            grand_rent += m_rent
            grand_market += m_market
            grand_ltl += m_ltl

            mgr_overviews.append(
                ManagerOverview(
                    manager_id=mgr.id,
                    manager_name=mgr.name,
                    portfolio_count=len(portfolios),
                    property_count=len(all_props),
                    total_units=m_units,
                    occupied=m_occ,
                    vacant=m_vac,
                    occupancy_rate=round(m_occ / m_units, 3) if m_units else 0,
                    total_monthly_rent=float(m_rent),
                    total_market_rent=float(m_market),
                    loss_to_lease=float(m_ltl),
                )
            )

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

    async def delinquency_board(self, manager_id: str | None = None) -> DelinquencyBoard:
        tenants = await self._ps.list_tenants()

        all_lease_lists = await asyncio.gather(
            *[self._ps.list_leases(tenant_id=t.id) for t in tenants]
        )

        tenant_context: dict[str, tuple[str, str]] = {}
        if manager_id:
            allowed_property_ids = await self._property_ids_for_manager(manager_id)
            filtered = []
            for t, leases in zip(tenants, all_lease_lists, strict=True):
                if any(le.property_id in allowed_property_ids for le in leases):
                    filtered.append(t)
            tenants = filtered

        lease_by_tenant: dict[str, tuple[str, str]] = {}
        for t, leases in zip(
            (await self._ps.list_tenants()),
            all_lease_lists,
            strict=True,
        ):
            if leases:
                le = leases[0]
                lease_by_tenant[t.id] = (le.property_id, le.unit_id)

        prop_ids = list({pid for pid, _ in lease_by_tenant.values()})
        unit_ids = list({uid for _, uid in lease_by_tenant.values()})
        props_list, units_list = await asyncio.gather(
            asyncio.gather(*[self._ps.get_property(pid) for pid in prop_ids]),
            asyncio.gather(*[self._ps.get_unit(uid) for uid in unit_ids]),
        )
        prop_map = {pid: p for pid, p in zip(prop_ids, props_list, strict=True) if p}
        unit_map = {uid: u for uid, u in zip(unit_ids, units_list, strict=True) if u}

        for tid, (pid, uid) in lease_by_tenant.items():
            prop = prop_map.get(pid)
            unit = unit_map.get(uid)
            tenant_context[tid] = (
                prop.name if prop else pid,
                unit.unit_number if unit else uid,
            )

        delinquent = [t for t in tenants if t.balance_owed > 0]
        delinquent.sort(key=lambda t: t.balance_owed, reverse=True)

        delinquency_notes: dict[str, str] = {}
        if self._ks is not None:
            delinquency_notes = await self._load_delinquency_notes([t.id for t in delinquent])

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
                    last_payment_date=t.last_payment_date.isoformat()
                    if t.last_payment_date
                    else None,
                    tags=t.tags,
                    delinquency_notes=delinquency_notes.get(t.id),
                )
                for t in delinquent
            ],
        )

    async def _load_delinquency_notes(self, tenant_ids: list[str]) -> dict[str, str]:
        """Read-time join: fetch delinquency_notes from ingested KB entities."""
        assert self._ks is not None
        result: dict[str, str] = {}
        lookup = set(tenant_ids)
        for ns_key in list(self._ks._entities.keys()) if hasattr(self._ks, "_entities") else []:
            if not ns_key.startswith("doc:"):
                continue
            entities = await self._ks.find_entities(
                ns_key,
                entity_type="appfolio_delinquent_tenant",
                limit=500,
            )
            for entity in entities:
                if entity.entity_id in lookup:
                    notes = entity.properties.get("delinquency_notes")
                    if notes:
                        result[entity.entity_id] = notes
        return result

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

        tenant_ids = list({le.tenant_id for le in expiring})
        prop_ids = list({le.property_id for le in expiring})
        unit_ids = list({le.unit_id for le in expiring})

        tenants_res, props_res, units_res = await asyncio.gather(
            asyncio.gather(*[self._ps.get_tenant(tid) for tid in tenant_ids]),
            asyncio.gather(*[self._ps.get_property(pid) for pid in prop_ids]),
            asyncio.gather(*[self._ps.get_unit(uid) for uid in unit_ids]),
        )
        tenant_map = {tid: t for tid, t in zip(tenant_ids, tenants_res, strict=True) if t}
        prop_map = {pid: p for pid, p in zip(prop_ids, props_res, strict=True) if p}
        unit_map = {uid: u for uid, u in zip(unit_ids, units_res, strict=True) if u}

        items: list[ExpiringLease] = []
        mtm_count = 0
        for le in expiring:
            tenant = tenant_map.get(le.tenant_id)
            prop = prop_map.get(le.property_id)
            unit = unit_map.get(le.unit_id)
            if le.is_month_to_month:
                mtm_count += 1
            items.append(
                ExpiringLease(
                    lease_id=le.id,
                    tenant_name=tenant.name if tenant else le.tenant_id,
                    property_name=prop.name if prop else le.property_id,
                    unit_number=unit.unit_number if unit else le.unit_id,
                    monthly_rent=float(le.monthly_rent),
                    market_rent=float(le.market_rent),
                    end_date=le.end_date.isoformat(),
                    days_left=(le.end_date - today).days,
                    is_month_to_month=le.is_month_to_month,
                )
            )

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
            if is_occupied(u):
                occ += 1
            else:
                vac += 1

            total_rent += u.current_rent
            total_market += u.market_rent
            total_ltl += loss_to_lease(u)

            unit_leases = [
                le for le in all_leases if le.unit_id == u.id and le.status == LeaseStatus.ACTIVE
            ]
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

            rows.append(
                RentRollUnit(
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
                )
            )

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

    async def vacancy_tracker(self, manager_id: str | None = None) -> VacancyTracker:
        all_units = await self._ps.list_units()

        if manager_id:
            allowed = await self._property_ids_for_manager(manager_id)
            all_units = [u for u in all_units if u.property_id in allowed]

        filtered_units = []
        notice_count = 0
        total_risk = Decimal("0")
        days_list: list[int] = []

        for u in all_units:
            is_unit_vacant = (
                u.occupancy_status
                in (OccupancyStatus.VACANT_RENTED, OccupancyStatus.VACANT_UNRENTED)
                if u.occupancy_status
                else u.status == UnitStatus.VACANT
            )
            is_notice = (
                u.occupancy_status
                in (OccupancyStatus.NOTICE_RENTED, OccupancyStatus.NOTICE_UNRENTED)
                if u.occupancy_status
                else False
            )
            if not (is_unit_vacant or is_notice):
                continue
            if is_notice:
                notice_count += 1
            total_risk += u.market_rent
            if u.days_vacant is not None:
                days_list.append(u.days_vacant)
            filtered_units.append(u)

        unique_prop_ids = list({u.property_id for u in filtered_units})
        props = await asyncio.gather(*[self._ps.get_property(pid) for pid in unique_prop_ids])
        prop_map = {pid: p for pid, p in zip(unique_prop_ids, props, strict=True) if p}

        vacant_units: list[VacantUnit] = []
        for u in filtered_units:
            prop = prop_map.get(u.property_id)
            vacant_units.append(
                VacantUnit(
                    unit_id=u.id,
                    unit_number=u.unit_number,
                    property_id=u.property_id,
                    property_name=prop.name if prop else u.property_id,
                    occupancy_status=u.occupancy_status.value if u.occupancy_status else "vacant",
                    days_vacant=u.days_vacant,
                    market_rent=float(u.market_rent),
                    listed_on_website=u.listed_on_website,
                    listed_on_internet=u.listed_on_internet,
                )
            )

        vacant_units.sort(key=lambda v: v.days_vacant or 0, reverse=True)

        return VacancyTracker(
            total_vacant=len(
                [
                    v
                    for v in vacant_units
                    if v.occupancy_status not in ("notice_rented", "notice_unrented")
                ]
            ),
            total_notice=notice_count,
            total_market_rent_at_risk=float(total_risk),
            avg_days_vacant=round(sum(days_list) / len(days_list), 1) if days_list else None,
            units=vacant_units,
        )

    async def _property_ids_for_manager(self, manager_id: str) -> set[str]:
        portfolios = await self._ps.list_portfolios(manager_id=manager_id)
        pf_props = await asyncio.gather(
            *[self._ps.list_properties(portfolio_id=pf.id) for pf in portfolios]
        )
        return {p.id for props in pf_props for p in props}
