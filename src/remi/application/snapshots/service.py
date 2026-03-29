"""SnapshotService — captures and retrieves PM performance snapshots.

After each document upload, a snapshot of every active PM's key metrics
is recorded with a timestamp.  The frontend uses these to show trends
(week-over-week occupancy, revenue, delinquency, etc.).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from remi.domain.properties.enums import OccupancyStatus, UnitStatus
from remi.domain.properties.ports import PropertyStore


class ManagerSnapshot(BaseModel, frozen=True):
    manager_id: str
    manager_name: str
    timestamp: datetime
    property_count: int = 0
    total_units: int = 0
    occupied: int = 0
    vacant: int = 0
    occupancy_rate: float = 0.0
    total_rent: float = 0.0
    total_market_rent: float = 0.0
    loss_to_lease: float = 0.0
    delinquent_count: int = 0
    delinquent_balance: float = 0.0


class SnapshotService:
    """Captures and stores PM performance snapshots in memory."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store
        self._snapshots: list[ManagerSnapshot] = []

    async def capture(self) -> list[ManagerSnapshot]:
        """Take a snapshot of all managers' current metrics."""
        now = datetime.now(UTC)
        managers = await self._ps.list_managers()
        batch: list[ManagerSnapshot] = []

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            prop_count = 0
            total_u = 0
            occ = 0
            vac = 0
            rent = Decimal("0")
            market = Decimal("0")
            ltl = Decimal("0")

            for pf in portfolios:
                props = await self._ps.list_properties(portfolio_id=pf.id)
                prop_count += len(props)
                for prop in props:
                    units = await self._ps.list_units(property_id=prop.id)
                    for u in units:
                        total_u += 1
                        if u.status == UnitStatus.OCCUPIED or (
                            u.occupancy_status == OccupancyStatus.OCCUPIED
                        ):
                            occ += 1
                        elif u.status == UnitStatus.VACANT or (
                            u.occupancy_status
                            and u.occupancy_status
                            in (OccupancyStatus.VACANT_RENTED, OccupancyStatus.VACANT_UNRENTED)
                        ):
                            vac += 1
                        rent += u.current_rent
                        market += u.market_rent
                        if u.current_rent < u.market_rent:
                            ltl += u.market_rent - u.current_rent

            del_count = 0
            del_balance = Decimal("0")
            tenants = await self._ps.list_tenants()
            allowed_pids: set[str] = set()
            for pf in portfolios:
                for p in await self._ps.list_properties(portfolio_id=pf.id):
                    allowed_pids.add(p.id)
            for t in tenants:
                if t.balance_owed <= 0:
                    continue
                leases = await self._ps.list_leases(tenant_id=t.id)
                if any(le.property_id in allowed_pids for le in leases):
                    del_count += 1
                    del_balance += t.balance_owed

            snap = ManagerSnapshot(
                manager_id=mgr.id,
                manager_name=mgr.name,
                timestamp=now,
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
            batch.append(snap)

        self._snapshots.extend(batch)
        return batch

    def get_history(self, manager_id: str | None = None) -> list[ManagerSnapshot]:
        """Return stored snapshots, optionally filtered by manager."""
        if manager_id:
            return [s for s in self._snapshots if s.manager_id == manager_id]
        return list(self._snapshots)

    def latest(self, manager_id: str) -> ManagerSnapshot | None:
        """Most recent snapshot for a given manager."""
        matching = [s for s in self._snapshots if s.manager_id == manager_id]
        return matching[-1] if matching else None

    def previous(self, manager_id: str) -> ManagerSnapshot | None:
        """Second-most-recent snapshot (for computing deltas)."""
        matching = [s for s in self._snapshots if s.manager_id == manager_id]
        return matching[-2] if len(matching) >= 2 else None
