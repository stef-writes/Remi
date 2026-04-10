"""Portfolio — portfolio-wide dashboard overview and needs-manager query."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from remi.application.core.models import OccupancyStatus, Unit
from remi.application.core.protocols import PropertyStore
from remi.application.core.rules import active_lease, is_occupied, loss_to_lease

from .properties import property_ids_for_manager
from .views import (
    DashboardOverview,
    ManagerMetrics,
    ManagerOverview,
    NeedsManagerResult,
    PropertyOverview,
    UnassignedProperty,
)


def _group_by_unit(leases: list) -> dict[str, list]:
    result: dict[str, list] = {}
    for le in leases:
        result.setdefault(le.unit_id, []).append(le)
    return result


def _is_unit_occupied(u: Unit, unit_leases: list) -> bool:
    """True when the unit has an active lease OR the rent roll flagged it occupied.

    Matches the logic in managers.py — lease evidence is primary,
    Unit.occupancy_status from the rent roll is the fallback.
    """
    if is_occupied(unit_leases):
        return True
    return u.occupancy_status in (
        OccupancyStatus.OCCUPIED,
        OccupancyStatus.NOTICE_RENTED,
        OccupancyStatus.NOTICE_UNRENTED,
    )


class DashboardBuilder:
    """Property/unit-centric portfolio overview."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

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

        allowed: set[str] | None = property_ids
        if allowed is None and manager_id:
            allowed = await property_ids_for_manager(self._ps, manager_id)
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

        all_unit_lists, all_lease_lists, all_maint_lists, all_obs_lists = (
            await asyncio.gather(
                asyncio.gather(*[self._ps.list_units(property_id=p.id) for p in all_properties]),
                asyncio.gather(*[self._ps.list_leases(property_id=p.id) for p in all_properties]),
                asyncio.gather(
                    *[self._ps.list_maintenance_requests(property_id=p.id) for p in all_properties]
                ),
                asyncio.gather(
                    *[self._ps.list_balance_observations(property_id=p.id) for p in all_properties]
                ),
            )
        )

        managers_list = await self._ps.list_managers()
        mgr_map = {m.id: m for m in managers_list}

        prop_overviews: list[PropertyOverview] = []
        prop_source_idx: list[int] = []  # maps prop_overviews index → all_properties index
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
            obs_list = all_obs_lists[i]

            known_units = len(unit_list)
            if known_units == 0:
                continue

            leases_by_unit = _group_by_unit(lease_list)

            # Confirmed occupants: tenants with an active lease OR a balance observation.
            lease_tenant_ids: set[str] = {
                le.tenant_id
                for le in lease_list
                if le.tenant_id and active_lease([le]) is not None
            }
            balance_tenant_ids: set[str] = {obs.tenant_id for obs in obs_list}
            confirmed_count = len(lease_tenant_ids | balance_tenant_ids)

            p_units = max(known_units, prop.unit_count or 0, confirmed_count)
            p_occ_from_units = 0
            p_rent = Decimal("0")
            p_market = Decimal("0")
            p_ltl = Decimal("0")
            p_open_maint = sum(
                1 for mr in maint_list if mr.status.value in ("open", "in_progress")
            )

            for u in unit_list:
                unit_leases = leases_by_unit.get(u.id, [])
                act = active_lease(unit_leases)
                lease_rent = act.monthly_rent if act else Decimal("0")
                if _is_unit_occupied(u, unit_leases):
                    p_occ_from_units += 1
                p_rent += lease_rent
                p_market += u.market_rent
                p_ltl += loss_to_lease(u.market_rent, lease_rent)

            p_occ = min(max(p_occ_from_units, confirmed_count), p_units)
            p_vac = p_units - p_occ

            mgr = mgr_map.get(prop.manager_id) if prop.manager_id else None
            ov_idx = len(prop_overviews)
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
            prop_source_idx.append(i)

            grand_units += p_units
            grand_occ += p_occ
            grand_vac += p_vac
            grand_rent += p_rent
            grand_market += p_market
            grand_ltl += p_ltl
            mgr_accum.setdefault(prop.manager_id, []).append(ov_idx)

        mgr_overviews: list[ManagerOverview] = []
        for mgr_id_key, indices in mgr_accum.items():
            po = [prop_overviews[idx] for idx in indices]
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
                src = prop_source_idx[idx]
                for le in all_lease_lists[src]:
                    if le.status.value == "active" and le.end_date <= deadline_90:
                        m_expiring += 1

            mgr = mgr_map.get(mgr_id_key) if mgr_id_key else None
            mgr_overviews.append(
                ManagerOverview(
                    manager_id=mgr_id_key or "unassigned",
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
            total_properties=len(prop_overviews),
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

    async def needs_manager(self) -> NeedsManagerResult:
        """Properties not assigned to any manager."""
        all_props = await self._ps.list_properties()
        items = [
            UnassignedProperty(id=p.id, name=p.name, address=p.address.one_line())
            for p in all_props
            if not p.manager_id
        ]
        return NeedsManagerResult(total=len(items), properties=items)
