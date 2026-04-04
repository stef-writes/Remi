"""SnapshotService — captures and retrieves PM performance rollups.

After each document upload, a snapshot of every active PM's key metrics
is recorded with a timestamp.  The frontend uses these to show trends
(week-over-week occupancy, revenue, delinquency, etc.).

Both manager-level and property-level rollups are produced in each
``capture()`` walk and persisted via the injected ``RollupStore``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from remi.application.core.protocols import PropertyStore
from remi.application.core.rules import (
    is_maintenance_open,
    is_occupied,
    is_vacant,
    loss_to_lease,
)
from remi.application.services.monitoring.snapshots.rollups import ManagerSnapshot, PropertySnapshot, RollupStore


class SnapshotService:
    """Captures and stores PM and property performance rollups."""

    def __init__(
        self,
        property_store: PropertyStore,
        rollup_store: RollupStore | None = None,
    ) -> None:
        self._ps = property_store
        self._store = rollup_store

    async def capture(
        self,
        *,
        effective_date: date | None = None,
    ) -> list[ManagerSnapshot]:
        """Take a snapshot of all managers' current metrics.

        Produces both manager and property snapshot DTOs in a single
        portfolio walk and persists them via the rollup store.

        *effective_date* — the business period the triggering document
        covers. Falls back to today when not provided so that
        trend analysis tracks report periods, not upload cadence.
        """
        now = datetime.now(UTC)
        eff_date = effective_date or now.date()
        managers = await self._ps.list_managers()
        manager_batch: list[ManagerSnapshot] = []
        property_batch: list[PropertySnapshot] = []

        # Pre-fetch delinquency data once for all managers.
        all_tenants = await self._ps.list_tenants()
        delinquent_tenants = [t for t in all_tenants if t.balance_owed > 0]
        tenant_property_ids: dict[str, set[str]] = {}
        for t in delinquent_tenants:
            leases = await self._ps.list_leases(tenant_id=t.id)
            tenant_property_ids[t.id] = {le.property_id for le in leases if le.property_id}

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            prop_count = 0
            total_u = 0
            occ = 0
            vac = 0
            rent = Decimal("0")
            market = Decimal("0")
            ltl = Decimal("0")
            mgr_property_ids: set[str] = set()

            for pf in portfolios:
                props = await self._ps.list_properties(portfolio_id=pf.id)
                prop_count += len(props)

                for prop in props:
                    mgr_property_ids.add(prop.id)
                    units = await self._ps.list_units(property_id=prop.id)
                    p_occ = 0
                    p_vac = 0
                    p_rent = Decimal("0")
                    p_market = Decimal("0")
                    p_ltl = Decimal("0")

                    for u in units:
                        total_u += 1
                        if is_occupied(u):
                            occ += 1
                            p_occ += 1
                        elif is_vacant(u):
                            vac += 1
                            p_vac += 1
                        rent += u.current_rent
                        market += u.market_rent
                        p_rent += u.current_rent
                        p_market += u.market_rent
                        u_ltl = loss_to_lease(u)
                        ltl += u_ltl
                        p_ltl += u_ltl

                    p_total = p_occ + p_vac
                    maint_requests = await self._ps.list_maintenance_requests(property_id=prop.id)
                    maint_open = sum(1 for r in maint_requests if is_maintenance_open(r))
                    maint_closed = len(maint_requests) - maint_open
                    costs = [float(r.cost) for r in maint_requests if r.cost and float(r.cost) > 0]
                    avg_cost = sum(costs) / len(costs) if costs else 0.0

                    property_batch.append(
                        PropertySnapshot(
                            property_id=prop.id,
                            property_name=prop.name,
                            manager_id=mgr.id,
                            manager_name=mgr.name,
                            timestamp=now,
                            effective_date=eff_date,
                            total_units=len(units),
                            occupied=p_occ,
                            vacant=p_vac,
                            occupancy_rate=round(p_occ / p_total, 3) if p_total else 0.0,
                            total_rent=float(p_rent),
                            total_market_rent=float(p_market),
                            loss_to_lease=float(p_ltl),
                            maintenance_open=maint_open,
                            maintenance_closed=maint_closed,
                            avg_maintenance_cost=round(avg_cost, 2),
                        )
                    )

            del_count = 0
            del_balance = Decimal("0")
            for t in delinquent_tenants:
                if tenant_property_ids[t.id] & mgr_property_ids:
                    del_count += 1
                    del_balance += t.balance_owed

            manager_batch.append(
                ManagerSnapshot(
                    manager_id=mgr.id,
                    manager_name=mgr.name,
                    timestamp=now,
                    effective_date=eff_date,
                    property_count=prop_count,
                    total_units=total_u,
                    occupied=occ,
                    vacant=vac,
                    occupancy_rate=round(occ / total_u, 3) if total_u else 0.0,
                    total_rent=float(rent),
                    total_market_rent=float(market),
                    loss_to_lease=float(ltl),
                    delinquent_count=del_count,
                    delinquent_balance=float(del_balance),
                )
            )

        if self._store is not None:
            await self._store.append_batch(manager_batch, property_batch)

        return manager_batch

    # ------------------------------------------------------------------
    # Manager queries
    # ------------------------------------------------------------------

    async def get_history(
        self,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[ManagerSnapshot]:
        """Return stored manager rollups, optionally filtered by manager and time."""
        if self._store is None:
            return []
        return await self._store.list_manager_snapshots(manager_id=manager_id, since=since)

    async def latest(self, manager_id: str) -> ManagerSnapshot | None:
        """Most recent manager rollup."""
        if self._store is None:
            return None
        return await self._store.latest_manager_snapshot(manager_id)

    async def previous(self, manager_id: str) -> ManagerSnapshot | None:
        """Second-most-recent manager rollup (for computing deltas)."""
        if self._store is None:
            return None
        return await self._store.previous_manager_snapshot(manager_id)

    # ------------------------------------------------------------------
    # Property queries
    # ------------------------------------------------------------------

    async def get_property_history(
        self,
        property_id: str | None = None,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[PropertySnapshot]:
        """Return stored property rollups with optional filters."""
        if self._store is None:
            return []
        return await self._store.list_property_snapshots(
            property_id=property_id,
            manager_id=manager_id,
            since=since,
        )
