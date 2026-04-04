"""Domain models and port for periodic metric rollups.

DTOs (``ManagerSnapshot``, ``PropertySnapshot``) represent point-in-time
aggregates captured after each document ingest.  ``RollupStore`` is the
abstract port that storage adapters implement.
"""

from __future__ import annotations

import abc
from datetime import date, datetime

from pydantic import BaseModel


class ManagerSnapshot(BaseModel, frozen=True):
    manager_id: str
    manager_name: str
    timestamp: datetime
    effective_date: date | None = None
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


class PropertySnapshot(BaseModel, frozen=True):
    property_id: str
    property_name: str
    manager_id: str
    manager_name: str
    timestamp: datetime
    effective_date: date | None = None
    total_units: int = 0
    occupied: int = 0
    vacant: int = 0
    occupancy_rate: float = 0.0
    total_rent: float = 0.0
    total_market_rent: float = 0.0
    loss_to_lease: float = 0.0
    maintenance_open: int = 0
    maintenance_closed: int = 0
    avg_maintenance_cost: float = 0.0


class RollupStore(abc.ABC):
    """Read/write access to manager and property metric rollups."""

    @abc.abstractmethod
    async def append_manager_snapshots(self, snapshots: list[ManagerSnapshot]) -> None: ...

    @abc.abstractmethod
    async def append_property_snapshots(self, snapshots: list[PropertySnapshot]) -> None: ...

    async def append_batch(
        self,
        managers: list[ManagerSnapshot],
        properties: list[PropertySnapshot],
    ) -> None:
        """Persist manager + property snapshots atomically.

        Default falls back to two separate calls; adapters with
        transactional support should override for atomicity.
        """
        await self.append_manager_snapshots(managers)
        await self.append_property_snapshots(properties)

    @abc.abstractmethod
    async def list_manager_snapshots(
        self,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[ManagerSnapshot]: ...

    @abc.abstractmethod
    async def list_property_snapshots(
        self,
        property_id: str | None = None,
        manager_id: str | None = None,
        since: datetime | None = None,
    ) -> list[PropertySnapshot]: ...

    @abc.abstractmethod
    async def latest_manager_snapshot(self, manager_id: str) -> ManagerSnapshot | None: ...

    @abc.abstractmethod
    async def previous_manager_snapshot(self, manager_id: str) -> ManagerSnapshot | None: ...
