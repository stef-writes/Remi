"""Rollup storage adapters — Postgres and in-memory.

Layer 1 (Facts): storage adapters only, no business logic.

Each adapter implements the ``RollupStore`` port from ``models.rollups``
and handles the mapping between domain DTOs and persistence-layer row types.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from remi.application.infra.stores.pg.tables import ManagerRollupRow, PropertyRollupRow
from remi.application.core.rollups import ManagerSnapshot, PropertySnapshot, RollupStore

# ------------------------------------------------------------------
# Row ↔ DTO converters
# ------------------------------------------------------------------


def _manager_row_from_dto(s: ManagerSnapshot) -> ManagerRollupRow:
    return ManagerRollupRow(
        id=uuid.uuid4().hex,
        manager_id=s.manager_id,
        manager_name=s.manager_name,
        captured_at=s.timestamp,
        property_count=s.property_count,
        total_units=s.total_units,
        occupied=s.occupied,
        vacant=s.vacant,
        occupancy_rate=s.occupancy_rate,
        total_rent=Decimal(str(s.total_rent)),
        total_market_rent=Decimal(str(s.total_market_rent)),
        loss_to_lease=Decimal(str(s.loss_to_lease)),
        delinquent_count=s.delinquent_count,
        delinquent_balance=Decimal(str(s.delinquent_balance)),
    )


def _manager_dto_from_row(row: ManagerRollupRow) -> ManagerSnapshot:
    return ManagerSnapshot(
        manager_id=row.manager_id,
        manager_name=row.manager_name,
        timestamp=row.captured_at,
        property_count=row.property_count,
        total_units=row.total_units,
        occupied=row.occupied,
        vacant=row.vacant,
        occupancy_rate=row.occupancy_rate,
        total_rent=float(row.total_rent),
        total_market_rent=float(row.total_market_rent),
        loss_to_lease=float(row.loss_to_lease),
        delinquent_count=row.delinquent_count,
        delinquent_balance=float(row.delinquent_balance),
    )


def _property_row_from_dto(s: PropertySnapshot) -> PropertyRollupRow:
    return PropertyRollupRow(
        id=uuid.uuid4().hex,
        property_id=s.property_id,
        property_name=s.property_name,
        manager_id=s.manager_id,
        manager_name=s.manager_name,
        captured_at=s.timestamp,
        total_units=s.total_units,
        occupied=s.occupied,
        vacant=s.vacant,
        occupancy_rate=s.occupancy_rate,
        total_rent=Decimal(str(s.total_rent)),
        total_market_rent=Decimal(str(s.total_market_rent)),
        loss_to_lease=Decimal(str(s.loss_to_lease)),
        maintenance_open=s.maintenance_open,
        maintenance_closed=s.maintenance_closed,
        avg_maintenance_cost=Decimal(str(s.avg_maintenance_cost)),
    )


def _property_dto_from_row(row: PropertyRollupRow) -> PropertySnapshot:
    return PropertySnapshot(
        property_id=row.property_id,
        property_name=row.property_name,
        manager_id=row.manager_id,
        manager_name=row.manager_name,
        timestamp=row.captured_at,
        total_units=row.total_units,
        occupied=row.occupied,
        vacant=row.vacant,
        occupancy_rate=row.occupancy_rate,
        total_rent=float(row.total_rent),
        total_market_rent=float(row.total_market_rent),
        loss_to_lease=float(row.loss_to_lease),
        maintenance_open=row.maintenance_open,
        maintenance_closed=row.maintenance_closed,
        avg_maintenance_cost=float(row.avg_maintenance_cost),
    )


# ------------------------------------------------------------------
# Postgres adapter
# ------------------------------------------------------------------


class PostgresRollupStore(RollupStore):
    """Postgres-backed rollup store using SQLModel async sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def append_manager_snapshots(self, snapshots: list[ManagerSnapshot]) -> None:
        async with self._session_factory() as session:
            for s in snapshots:
                session.add(_manager_row_from_dto(s))
            await session.commit()

    async def append_property_snapshots(self, snapshots: list[PropertySnapshot]) -> None:
        async with self._session_factory() as session:
            for s in snapshots:
                session.add(_property_row_from_dto(s))
            await session.commit()

    async def append_batch(
        self,
        managers: list[ManagerSnapshot],
        properties: list[PropertySnapshot],
    ) -> None:
        async with self._session_factory() as session:
            for s in managers:
                session.add(_manager_row_from_dto(s))
            for s in properties:
                session.add(_property_row_from_dto(s))
            await session.commit()

    async def list_manager_snapshots(
        self,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[ManagerSnapshot]:
        async with self._session_factory() as session:
            stmt = select(ManagerRollupRow)
            if manager_id:
                stmt = stmt.where(ManagerRollupRow.manager_id == manager_id)
            if since:
                stmt = stmt.where(ManagerRollupRow.captured_at >= since)
            stmt = stmt.order_by(ManagerRollupRow.captured_at, ManagerRollupRow.id)
            result = await session.execute(stmt)
            return [_manager_dto_from_row(r) for r in result.scalars().all()]

    async def list_property_snapshots(
        self,
        property_id: str | None = None,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[PropertySnapshot]:
        async with self._session_factory() as session:
            stmt = select(PropertyRollupRow)
            if property_id:
                stmt = stmt.where(PropertyRollupRow.property_id == property_id)
            if manager_id:
                stmt = stmt.where(PropertyRollupRow.manager_id == manager_id)
            if since:
                stmt = stmt.where(PropertyRollupRow.captured_at >= since)
            stmt = stmt.order_by(PropertyRollupRow.captured_at, PropertyRollupRow.id)
            result = await session.execute(stmt)
            return [_property_dto_from_row(r) for r in result.scalars().all()]

    async def latest_manager_snapshot(self, manager_id: str) -> ManagerSnapshot | None:
        async with self._session_factory() as session:
            stmt = (
                select(ManagerRollupRow)
                .where(ManagerRollupRow.manager_id == manager_id)
                .order_by(ManagerRollupRow.captured_at.desc(), ManagerRollupRow.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalars().first()
            return _manager_dto_from_row(row) if row else None

    async def previous_manager_snapshot(self, manager_id: str) -> ManagerSnapshot | None:
        async with self._session_factory() as session:
            stmt = (
                select(ManagerRollupRow)
                .where(ManagerRollupRow.manager_id == manager_id)
                .order_by(ManagerRollupRow.captured_at.desc(), ManagerRollupRow.id.desc())
                .offset(1)
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalars().first()
            return _manager_dto_from_row(row) if row else None


# ------------------------------------------------------------------
# In-memory adapter (tests / dev)
# ------------------------------------------------------------------


class InMemoryRollupStore(RollupStore):
    """Non-durable in-memory rollup store for tests and dev."""

    def __init__(self) -> None:
        self._manager: list[ManagerSnapshot] = []
        self._property: list[PropertySnapshot] = []

    def dump_state(self) -> dict[str, list[dict[str, object]]]:
        return {
            "manager": [s.model_dump(mode="json") for s in self._manager],
            "property": [s.model_dump(mode="json") for s in self._property],
        }

    def load_state(self, data: dict[str, list[dict[str, object]]]) -> None:
        self._manager.clear()
        self._property.clear()
        for raw in data.get("manager", []):
            self._manager.append(ManagerSnapshot.model_validate(raw))
        for raw in data.get("property", []):
            self._property.append(PropertySnapshot.model_validate(raw))

    async def append_manager_snapshots(self, snapshots: list[ManagerSnapshot]) -> None:
        self._manager.extend(snapshots)

    async def append_property_snapshots(self, snapshots: list[PropertySnapshot]) -> None:
        self._property.extend(snapshots)

    async def list_manager_snapshots(
        self,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[ManagerSnapshot]:
        rows = self._manager
        if manager_id:
            rows = [r for r in rows if r.manager_id == manager_id]
        if since:
            since_utc = since if since.tzinfo else since.replace(tzinfo=UTC)
            rows = [r for r in rows if _ensure_tz(r.timestamp) >= since_utc]
        return sorted(rows, key=lambda r: r.timestamp)

    async def list_property_snapshots(
        self,
        property_id: str | None = None,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[PropertySnapshot]:
        rows = self._property
        if property_id:
            rows = [r for r in rows if r.property_id == property_id]
        if manager_id:
            rows = [r for r in rows if r.manager_id == manager_id]
        if since:
            since_utc = since if since.tzinfo else since.replace(tzinfo=UTC)
            rows = [r for r in rows if _ensure_tz(r.timestamp) >= since_utc]
        return sorted(rows, key=lambda r: r.timestamp)

    async def latest_manager_snapshot(self, manager_id: str) -> ManagerSnapshot | None:
        matching = sorted(
            (r for r in self._manager if r.manager_id == manager_id),
            key=lambda r: r.timestamp,
        )
        return matching[-1] if matching else None

    async def previous_manager_snapshot(self, manager_id: str) -> ManagerSnapshot | None:
        matching = sorted(
            (r for r in self._manager if r.manager_id == manager_id),
            key=lambda r: r.timestamp,
        )
        return matching[-2] if len(matching) >= 2 else None


def _ensure_tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
