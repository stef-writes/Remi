"""DashboardResolver — five typed dashboard views over PropertyStore.

Zero LLM imports. Zero document store imports. Pure aggregation.
Occupancy, current rent, and balance are all derived at query time from
Lease and BalanceObservation records — never read from Unit or Tenant fields.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from remi.application.core.models import (
    BalanceObservation,
    LeaseStatus,
)
from remi.application.core.protocols import KnowledgeReader, PropertyStore
from remi.application.core.rules import (
    active_lease,
    derive_occupancy_status,
    is_occupied,
    is_vacant,
    loss_to_lease,
)

from ._models import (
    DashboardOverview,
    DelinquencyBoard,
    DelinquencyTrend,
    DelinquentTenant,
    ExpiringLease,
    LeaseCalendar,
    MaintenanceTrend,
    MaintenanceTrendPeriod,
    ManagerMetrics,
    ManagerOverview,
    NeedsManagerResult,
    OccupancyTrend,
    OccupancyTrendPeriod,
    PropertyOverview,
    RentTrend,
    RentTrendPeriod,
    TrendPeriod,
    UnassignedProperty,
    VacancyTracker,
    VacantUnit,
)
from .scope import property_ids_for_manager


def _compute_direction(values: list[float]) -> str:
    """Determine if a series is improving, worsening, or stable."""
    if len(values) < 2:
        return "insufficient_data"
    first_half = values[: len(values) // 2]
    second_half = values[len(values) // 2 :]
    if not first_half or not second_half:
        return "insufficient_data"
    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)
    if avg_first == 0:
        return "stable" if avg_second == 0 else "worsening"
    pct_change = (avg_second - avg_first) / abs(avg_first)
    if pct_change > 0.05:
        return "worsening"
    if pct_change < -0.05:
        return "improving"
    return "stable"


def _compute_direction_inverse(values: list[float]) -> str:
    """Same as _compute_direction but higher = improving (occupancy, rent)."""
    raw = _compute_direction(values)
    if raw == "worsening":
        return "improving"
    if raw == "improving":
        return "worsening"
    return raw


def _group_leases_by_unit(leases: list) -> dict[str, list]:
    result: dict[str, list] = {}
    for le in leases:
        result.setdefault(le.unit_id, []).append(le)
    return result


def _latest_obs_by_tenant(
    obs_list: list[BalanceObservation],
) -> dict[str, BalanceObservation]:
    latest: dict[str, BalanceObservation] = {}
    for obs in obs_list:
        existing = latest.get(obs.tenant_id)
        if existing is None or obs.observed_at > existing.observed_at:
            latest[obs.tenant_id] = obs
    return latest


class DashboardResolver:
    """Pure PropertyStore aggregation — no LLM, no document store."""

    def __init__(
        self,
        property_store: PropertyStore,
        knowledge_reader: KnowledgeReader | None = None,
    ) -> None:
        self._ps = property_store
        self._kr = knowledge_reader

    async def _resolve_property_ids(
        self,
        *,
        property_ids: set[str] | None = None,
        manager_id: str | None = None,
    ) -> set[str] | None:
        if property_ids is not None:
            return property_ids
        if manager_id:
            return await property_ids_for_manager(self._ps, manager_id)
        return None

    async def dashboard_overview(
        self,
        manager_id: str | None = None,
        property_ids: set[str] | None = None,
    ) -> DashboardOverview:
        """Property/unit-centric overview.

        Properties are the primary axis; managers are an optional grouping.
        Properties without a manager still contribute to grand totals.
        """
        today = date.today()
        deadline_90 = today + timedelta(days=90)

        if manager_id:
            all_properties = await self._ps.list_properties(manager_id=manager_id)
        else:
            all_properties = await self._ps.list_properties()

        allowed = await self._resolve_property_ids(property_ids=property_ids, manager_id=manager_id)
        if allowed is not None:
            all_properties = [p for p in all_properties if p.id in allowed]

        if not all_properties:
            return DashboardOverview(
                total_properties=0,
                total_units=0,
                occupied=0,
                vacant=0,
                occupancy_rate=0,
                total_monthly_rent=0.0,
                total_market_rent=0.0,
                total_loss_to_lease=0.0,
                properties=[],
            )

        all_unit_lists, all_lease_lists, all_maint_lists = await asyncio.gather(
            asyncio.gather(
                *[self._ps.list_units(property_id=p.id) for p in all_properties],
            ),
            asyncio.gather(
                *[self._ps.list_leases(property_id=p.id) for p in all_properties],
            ),
            asyncio.gather(
                *[self._ps.list_maintenance_requests(property_id=p.id) for p in all_properties],
            ),
        )

        managers_list = await self._ps.list_managers()
        mgr_map = {m.id: m for m in managers_list}

        prop_overviews: list[PropertyOverview] = []
        grand_units = 0
        grand_occ = 0
        grand_vac = 0
        grand_rent = Decimal("0")
        grand_market = Decimal("0")
        grand_ltl = Decimal("0")

        mgr_accum: dict[str | None, list[int]] = {}

        for i, prop in enumerate(all_properties):
            unit_list = all_unit_lists[i]
            lease_list = all_lease_lists[i]
            maint_list = all_maint_lists[i]

            leases_by_unit = _group_leases_by_unit(lease_list)
            p_units = len(unit_list)
            p_occ = 0
            p_vac = 0
            p_rent = Decimal("0")
            p_market = Decimal("0")
            p_ltl = Decimal("0")
            p_open_maint = sum(1 for mr in maint_list if mr.status.value in ("open", "in_progress"))

            for u in unit_list:
                unit_leases = leases_by_unit.get(u.id, [])
                act = active_lease(unit_leases)
                lease_rent = act.monthly_rent if act else Decimal("0")
                if is_occupied(unit_leases):
                    p_occ += 1
                elif is_vacant(unit_leases):
                    p_vac += 1
                p_rent += lease_rent
                p_market += u.market_rent
                p_ltl += loss_to_lease(u.market_rent, lease_rent)

            mgr = mgr_map.get(prop.manager_id) if prop.manager_id else None
            prop_overviews.append(
                PropertyOverview(
                    property_id=prop.id,
                    property_name=prop.name,
                    address=prop.address.one_line(),
                    manager_id=prop.manager_id,
                    manager_name=mgr.name if mgr else None,
                    total_units=p_units,
                    occupied=p_occ,
                    vacant=p_vac,
                    occupancy_rate=round(p_occ / p_units, 3) if p_units else 0,
                    monthly_rent=float(p_rent),
                    market_rent=float(p_market),
                    loss_to_lease=float(p_ltl),
                    open_maintenance=p_open_maint,
                )
            )

            grand_units += p_units
            grand_occ += p_occ
            grand_vac += p_vac
            grand_rent += p_rent
            grand_market += p_market
            grand_ltl += p_ltl

            mgr_accum.setdefault(prop.manager_id, []).append(i)

        # Build per-manager overviews (secondary grouping) before sorting
        mgr_overviews: list[ManagerOverview] = []
        for mgr_id, indices in mgr_accum.items():
            po = [prop_overviews[i] for i in indices]
            m_units = sum(p.total_units for p in po)
            m_occ = sum(p.occupied for p in po)
            m_vac = sum(p.vacant for p in po)
            m_rent = sum(Decimal(str(p.monthly_rent)) for p in po)
            m_market = sum(Decimal(str(p.market_rent)) for p in po)
            m_ltl_val = sum(Decimal(str(p.loss_to_lease)) for p in po)
            m_vacancy_loss = sum(
                Decimal(str(p.market_rent)) - Decimal(str(p.monthly_rent))
                for p in po
                if p.vacant > 0
            )
            m_open_maint = sum(p.open_maintenance for p in po)

            m_expiring = 0
            for idx in indices:
                for le in all_lease_lists[idx]:
                    if le.status.value == "active" and le.end_date <= deadline_90:
                        m_expiring += 1

            mgr = mgr_map.get(mgr_id) if mgr_id else None
            mgr_overviews.append(
                ManagerOverview(
                    manager_id=mgr_id or "unassigned",
                    manager_name=mgr.name if mgr else "Unassigned",
                    property_count=len(indices),
                    metrics=ManagerMetrics(
                        total_units=m_units,
                        occupied=m_occ,
                        vacant=m_vac,
                        occupancy_rate=round(m_occ / m_units, 3) if m_units else 0,
                        total_actual_rent=float(m_rent),
                        total_market_rent=float(m_market),
                        loss_to_lease=float(m_ltl_val),
                        vacancy_loss=float(m_vacancy_loss),
                        open_maintenance=m_open_maint,
                        expiring_leases_90d=m_expiring,
                    ),
                )
            )

        prop_overviews.sort(key=lambda p: p.total_units, reverse=True)

        mgr_overviews.sort(key=lambda m: m.metrics.total_units, reverse=True)

        return DashboardOverview(
            total_properties=len(all_properties),
            total_units=grand_units,
            occupied=grand_occ,
            vacant=grand_vac,
            occupancy_rate=round(grand_occ / grand_units, 3) if grand_units else 0,
            total_monthly_rent=float(grand_rent),
            total_market_rent=float(grand_market),
            total_loss_to_lease=float(grand_ltl),
            properties=prop_overviews,
            total_managers=sum(1 for m in mgr_overviews if m.manager_id != "unassigned"),
            managers=mgr_overviews,
        )

    async def delinquency_board(
        self,
        manager_id: str | None = None,
        property_ids: set[str] | None = None,
    ) -> DelinquencyBoard:
        allowed = await self._resolve_property_ids(property_ids=property_ids, manager_id=manager_id)

        all_obs = await self._ps.list_balance_observations()
        if allowed is not None:
            all_obs = [o for o in all_obs if o.property_id in allowed]

        latest_obs = _latest_obs_by_tenant(all_obs)
        delinquent = [obs for obs in latest_obs.values() if obs.balance_total > 0]
        delinquent.sort(key=lambda o: o.balance_total, reverse=True)

        tenant_ids = list({obs.tenant_id for obs in delinquent})
        lease_lists = await asyncio.gather(
            *[self._ps.list_leases(tenant_id=tid) for tid in tenant_ids]
        )
        lease_by_tenant: dict[str, tuple[str, str]] = {}
        for tid, leases in zip(tenant_ids, lease_lists, strict=True):
            if leases:
                le = leases[0]
                lease_by_tenant[tid] = (le.property_id, le.unit_id)

        prop_ids = list({pid for pid, _ in lease_by_tenant.values()})
        unit_ids = list({uid for _, uid in lease_by_tenant.values()})
        props_list, units_list = await asyncio.gather(
            asyncio.gather(*[self._ps.get_property(pid) for pid in prop_ids]),
            asyncio.gather(*[self._ps.get_unit(uid) for uid in unit_ids]),
        )
        prop_map = {pid: p for pid, p in zip(prop_ids, props_list, strict=True) if p}
        unit_map = {uid: u for uid, u in zip(unit_ids, units_list, strict=True) if u}

        tenants_list = await asyncio.gather(*[self._ps.get_tenant(tid) for tid in tenant_ids])
        tenant_map = {tid: t for tid, t in zip(tenant_ids, tenants_list, strict=True) if t}

        delinquency_notes: dict[str, str] = {}
        if self._kr is not None:
            delinquency_notes = await self._load_delinquency_notes(
                [obs.tenant_id for obs in delinquent]
            )

        result_items: list[DelinquentTenant] = []
        for obs in delinquent:
            tenant = tenant_map.get(obs.tenant_id)
            pid, uid = lease_by_tenant.get(obs.tenant_id, (None, None))
            prop = prop_map.get(pid) if pid else None
            unit = unit_map.get(uid) if uid else None
            result_items.append(
                DelinquentTenant(
                    tenant_id=obs.tenant_id,
                    tenant_name=tenant.name if tenant else obs.tenant_id,
                    status=tenant.status.value if tenant else "current",
                    property_id=pid,
                    property_name=prop.name if prop else (pid or ""),
                    unit_id=uid,
                    unit_number=unit.unit_number if unit else (uid or ""),
                    balance_owed=float(obs.balance_total),
                    balance_0_30=float(obs.balance_0_30),
                    balance_30_plus=float(obs.balance_30_plus),
                    last_payment_date=obs.last_payment_date.isoformat()
                    if obs.last_payment_date
                    else None,
                    delinquency_notes=delinquency_notes.get(obs.tenant_id),
                )
            )

        return DelinquencyBoard(
            total_delinquent=len(result_items),
            total_balance=float(sum(obs.balance_total for obs in delinquent)),
            tenants=result_items,
        )

    async def _load_delinquency_notes(self, tenant_ids: list[str]) -> dict[str, str]:
        assert self._kr is not None
        result: dict[str, str] = {}
        lookup = set(tenant_ids)
        namespaces = await self._kr.list_namespaces()
        for ns_key in namespaces:
            if not ns_key.startswith("doc:"):
                continue
            entities = await self._kr.find_entities(
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
        self,
        days: int = 90,
        manager_id: str | None = None,
        property_ids: set[str] | None = None,
    ) -> LeaseCalendar:
        today = date.today()
        deadline = today + timedelta(days=days)
        leases = await self._ps.list_leases(status=LeaseStatus.ACTIVE)

        allowed = await self._resolve_property_ids(property_ids=property_ids, manager_id=manager_id)
        if allowed is not None:
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
                    property_id=le.property_id,
                    property_name=prop.name if prop else le.property_id,
                    unit_id=le.unit_id,
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

    async def vacancy_tracker(
        self,
        manager_id: str | None = None,
        property_ids: set[str] | None = None,
    ) -> VacancyTracker:
        all_units = await self._ps.list_units()

        allowed = await self._resolve_property_ids(property_ids=property_ids, manager_id=manager_id)
        if allowed is not None:
            all_units = [u for u in all_units if u.property_id in allowed]

        if not all_units:
            return VacancyTracker(
                total_vacant=0,
                total_notice=0,
                total_market_rent_at_risk=0.0,
                avg_days_vacant=None,
                units=[],
            )

        prop_ids_set = {u.property_id for u in all_units}
        all_lease_lists = await asyncio.gather(
            *[self._ps.list_leases(property_id=pid) for pid in prop_ids_set]
        )
        leases_by_unit: dict[str, list] = {}
        for lease_list in all_lease_lists:
            for le in lease_list:
                leases_by_unit.setdefault(le.unit_id, []).append(le)

        today = date.today()
        filtered_units = []
        notice_count = 0
        total_risk = Decimal("0")
        days_list: list[int] = []

        for u in all_units:
            unit_leases = leases_by_unit.get(u.id, [])
            occ_status = derive_occupancy_status(unit_leases)

            is_unit_vacant = occ_status.value in (
                "vacant_rented",
                "vacant_unrented",
            )
            is_notice = occ_status.value in ("notice_rented", "notice_unrented")

            if not (is_unit_vacant or is_notice):
                continue
            if is_notice:
                notice_count += 1
            total_risk += u.market_rent

            # Compute days vacant from lease history
            ended = [
                le
                for le in unit_leases
                if le.status in (LeaseStatus.EXPIRED, LeaseStatus.TERMINATED)
            ]
            if ended:
                latest_end = max(le.end_date for le in ended)
                days_vacant = (today - latest_end).days
                if days_vacant >= 0:
                    days_list.append(days_vacant)
            else:
                days_vacant = None

            filtered_units.append((u, occ_status, days_vacant))

        unique_prop_ids = list({u.property_id for u, _, _ in filtered_units})
        props = await asyncio.gather(*[self._ps.get_property(pid) for pid in unique_prop_ids])
        prop_map = {pid: p for pid, p in zip(unique_prop_ids, props, strict=True) if p}

        vacant_units: list[VacantUnit] = []
        for u, occ_status, days_vacant in filtered_units:
            prop = prop_map.get(u.property_id)
            vacant_units.append(
                VacantUnit(
                    unit_id=u.id,
                    unit_number=u.unit_number,
                    property_id=u.property_id,
                    property_name=prop.name if prop else u.property_id,
                    occupancy_status=occ_status.value,
                    days_vacant=days_vacant,
                    market_rent=float(u.market_rent),
                )
            )

        vacant_units.sort(key=lambda v: v.days_vacant or 0, reverse=True)

        return VacancyTracker(
            total_vacant=sum(
                1
                for v in vacant_units
                if v.occupancy_status not in ("notice_rented", "notice_unrented")
            ),
            total_notice=notice_count,
            total_market_rent_at_risk=float(total_risk),
            avg_days_vacant=round(sum(days_list) / len(days_list), 1) if days_list else None,
            units=vacant_units,
        )

    async def delinquency_trend(
        self,
        manager_id: str | None = None,
        property_id: str | None = None,
        periods: int = 12,
    ) -> DelinquencyTrend:
        """Delinquency totals grouped by calendar month.

        Uses the full BalanceObservation history instead of collapsing to
        latest-per-tenant, so the agent can see how a manager's (or
        property's) delinquency has evolved across report uploads.
        """
        all_obs = await self._ps.list_balance_observations()

        if property_id:
            all_obs = [o for o in all_obs if o.property_id == property_id]
        elif manager_id:
            allowed = await property_ids_for_manager(self._ps, manager_id)
            if allowed:
                all_obs = [o for o in all_obs if o.property_id in allowed]

        by_month: dict[str, list[BalanceObservation]] = {}
        for obs in all_obs:
            key = obs.observed_at.strftime("%Y-%m")
            by_month.setdefault(key, []).append(obs)

        sorted_months = sorted(by_month.keys())[-periods:]
        trend_periods: list[TrendPeriod] = []
        for month in sorted_months:
            month_obs = by_month[month]
            latest_per_tenant = _latest_obs_by_tenant(month_obs)
            delinquent = [o for o in latest_per_tenant.values() if o.balance_total > 0]
            if not delinquent:
                trend_periods.append(
                    TrendPeriod(
                        period=month,
                        total_balance=0.0,
                        tenant_count=0,
                        avg_balance=0.0,
                        max_balance=0.0,
                    )
                )
                continue
            total = sum(float(o.balance_total) for o in delinquent)
            trend_periods.append(
                TrendPeriod(
                    period=month,
                    total_balance=round(total, 2),
                    tenant_count=len(delinquent),
                    avg_balance=round(total / len(delinquent), 2),
                    max_balance=round(max(float(o.balance_total) for o in delinquent), 2),
                )
            )

        direction = _compute_direction([p.total_balance for p in trend_periods])

        return DelinquencyTrend(
            manager_id=manager_id,
            periods=trend_periods,
            period_count=len(trend_periods),
            direction=direction,
        )

    async def occupancy_trend(
        self,
        manager_id: str | None = None,
        property_id: str | None = None,
        periods: int = 12,
    ) -> OccupancyTrend:
        """Occupancy rate over time derived from lease lifecycle timestamps.

        Groups leases by month of last_confirmed_at (or first_seen_at) to
        reconstruct what percentage of units were occupied in each period.
        """
        if property_id:
            properties = [await self._ps.get_property(property_id)]
            properties = [p for p in properties if p is not None]
        elif manager_id:
            properties = await self._ps.list_properties(manager_id=manager_id)
        else:
            properties = await self._ps.list_properties()

        all_units = await asyncio.gather(
            *[self._ps.list_units(property_id=p.id) for p in properties]
        )
        all_leases = await asyncio.gather(
            *[self._ps.list_leases(property_id=p.id) for p in properties]
        )

        total_unit_count = sum(len(ul) for ul in all_units)
        flat_leases = [le for lease_list in all_leases for le in lease_list]

        by_month: dict[str, set[str]] = {}
        for le in flat_leases:
            ts = le.last_confirmed_at or le.first_seen_at
            if ts is None:
                continue
            if le.status.value not in ("active", "expired", "terminated"):
                continue
            key = ts.strftime("%Y-%m")
            by_month.setdefault(key, set()).add(le.unit_id)

        sorted_months = sorted(by_month.keys())[-periods:]
        trend_periods: list[OccupancyTrendPeriod] = []
        for month in sorted_months:
            occupied = len(by_month[month])
            capped = min(occupied, total_unit_count)
            vacant = total_unit_count - capped
            trend_periods.append(
                OccupancyTrendPeriod(
                    period=month,
                    total_units=total_unit_count,
                    occupied=capped,
                    vacant=vacant,
                    occupancy_rate=round(capped / total_unit_count, 3) if total_unit_count else 0,
                )
            )

        direction = _compute_direction_inverse([p.occupancy_rate for p in trend_periods])

        return OccupancyTrend(
            manager_id=manager_id,
            property_id=property_id,
            periods=trend_periods,
            period_count=len(trend_periods),
            direction=direction,
        )

    async def rent_trend(
        self,
        manager_id: str | None = None,
        property_id: str | None = None,
        periods: int = 12,
    ) -> RentTrend:
        """Average and total rent over time derived from lease confirmations."""
        if property_id:
            properties = [await self._ps.get_property(property_id)]
            properties = [p for p in properties if p is not None]
        elif manager_id:
            properties = await self._ps.list_properties(manager_id=manager_id)
        else:
            properties = await self._ps.list_properties()

        all_leases = await asyncio.gather(
            *[self._ps.list_leases(property_id=p.id) for p in properties]
        )
        flat_leases = [le for lease_list in all_leases for le in lease_list]

        by_month: dict[str, list[float]] = {}
        for le in flat_leases:
            ts = le.last_confirmed_at or le.first_seen_at
            if ts is None or le.status.value not in ("active",):
                continue
            key = ts.strftime("%Y-%m")
            by_month.setdefault(key, []).append(float(le.monthly_rent))

        sorted_months = sorted(by_month.keys())[-periods:]
        trend_periods: list[RentTrendPeriod] = []
        for month in sorted_months:
            rents = sorted(by_month[month])
            total = sum(rents)
            count = len(rents)
            median = rents[count // 2] if count else 0.0
            trend_periods.append(
                RentTrendPeriod(
                    period=month,
                    avg_rent=round(total / count, 2) if count else 0.0,
                    median_rent=round(median, 2),
                    total_rent=round(total, 2),
                    unit_count=count,
                )
            )

        direction = _compute_direction_inverse([p.avg_rent for p in trend_periods])

        return RentTrend(
            manager_id=manager_id,
            property_id=property_id,
            periods=trend_periods,
            period_count=len(trend_periods),
            direction=direction,
        )

    async def maintenance_trend(
        self,
        manager_id: str | None = None,
        property_id: str | None = None,
        unit_id: str | None = None,
        periods: int = 12,
    ) -> MaintenanceTrend:
        """Maintenance volume, cost, and resolution time grouped by month.

        Groups requests by created_at (opened) and completed_date (completed).
        Computes net open delta, total cost, average resolution time, and
        per-category breakdown for each period.
        """
        requests = await self._ps.list_maintenance_requests(
            property_id=property_id,
            unit_id=unit_id,
            manager_id=manager_id,
        )

        opened_by_month: dict[str, list] = {}
        completed_by_month: dict[str, list] = {}
        for r in requests:
            open_key = r.created_at.strftime("%Y-%m")
            opened_by_month.setdefault(open_key, []).append(r)
            if r.completed_date:
                close_key = r.completed_date.strftime("%Y-%m")
                completed_by_month.setdefault(close_key, []).append(r)

        all_months = sorted(set(opened_by_month) | set(completed_by_month))[-periods:]

        trend_periods: list[MaintenanceTrendPeriod] = []
        for month in all_months:
            opened = opened_by_month.get(month, [])
            completed = completed_by_month.get(month, [])

            resolution_days: list[float] = []
            total_cost = sum(
                float(r.cost) for r in completed if r.cost
            )
            for r in completed:
                if r.completed_date and r.created_at:
                    delta = (r.completed_date - r.created_at.date()).days
                    if delta >= 0:
                        resolution_days.append(float(delta))

            by_category: dict[str, int] = {}
            for r in opened:
                cat = r.category.value
                by_category[cat] = by_category.get(cat, 0) + 1

            trend_periods.append(
                MaintenanceTrendPeriod(
                    period=month,
                    opened=len(opened),
                    completed=len(completed),
                    net_open=len(opened) - len(completed),
                    total_cost=round(total_cost, 2),
                    avg_resolution_days=(
                        round(sum(resolution_days) / len(resolution_days), 1)
                        if resolution_days
                        else None
                    ),
                    by_category=by_category,
                )
            )

        direction = _compute_direction(
            [float(p.opened) for p in trend_periods]
        )

        return MaintenanceTrend(
            manager_id=manager_id,
            property_id=property_id,
            unit_id=unit_id,
            periods=trend_periods,
            period_count=len(trend_periods),
            direction=direction,
        )

    async def needs_manager(self) -> NeedsManagerResult:
        """Properties not assigned to any manager."""
        all_props = await self._ps.list_properties()
        items = [
            UnassignedProperty(id=p.id, name=p.name, address=p.address.one_line())
            for p in all_props
            if not p.manager_id
        ]
        return NeedsManagerResult(total=len(items), properties=items)
