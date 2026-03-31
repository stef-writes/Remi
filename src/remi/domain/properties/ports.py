"""Repository ports for the real estate domain.

These abstract interfaces define how the domain accesses persistent
data. Infrastructure adapters provide concrete implementations
(in-memory, SQLite, Postgres, etc.).
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.domain.properties.enums import (
        LeaseStatus,
        MaintenanceStatus,
        OccupancyStatus,
        TenantStatus,
        UnitStatus,
    )
    from remi.domain.properties.models import (
        Lease,
        MaintenanceRequest,
        Portfolio,
        Property,
        PropertyManager,
        Tenant,
        Unit,
    )


class PropertyStore(abc.ABC):
    """Read/write access to the core property management entities."""

    # -- Property Managers --
    @abc.abstractmethod
    async def get_manager(self, manager_id: str) -> PropertyManager | None: ...

    @abc.abstractmethod
    async def list_managers(self) -> list[PropertyManager]: ...

    @abc.abstractmethod
    async def upsert_manager(self, manager: PropertyManager) -> None: ...

    # -- Portfolios --
    @abc.abstractmethod
    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None: ...

    @abc.abstractmethod
    async def list_portfolios(
        self, *, manager_id: str | None = None
    ) -> list[Portfolio]: ...

    @abc.abstractmethod
    async def upsert_portfolio(self, portfolio: Portfolio) -> None: ...

    # -- Properties --
    @abc.abstractmethod
    async def get_property(self, property_id: str) -> Property | None: ...

    @abc.abstractmethod
    async def list_properties(
        self, *, portfolio_id: str | None = None
    ) -> list[Property]: ...

    @abc.abstractmethod
    async def upsert_property(self, prop: Property) -> None: ...

    # -- Units --
    @abc.abstractmethod
    async def get_unit(self, unit_id: str) -> Unit | None: ...

    @abc.abstractmethod
    async def list_units(
        self,
        *,
        property_id: str | None = None,
        status: UnitStatus | None = None,
        occupancy_status: OccupancyStatus | None = None,
    ) -> list[Unit]: ...

    @abc.abstractmethod
    async def upsert_unit(self, unit: Unit) -> None: ...

    # -- Leases --
    @abc.abstractmethod
    async def get_lease(self, lease_id: str) -> Lease | None: ...

    @abc.abstractmethod
    async def list_leases(
        self,
        *,
        unit_id: str | None = None,
        tenant_id: str | None = None,
        property_id: str | None = None,
        status: LeaseStatus | None = None,
    ) -> list[Lease]: ...

    @abc.abstractmethod
    async def upsert_lease(self, lease: Lease) -> None: ...

    # -- Tenants --
    @abc.abstractmethod
    async def get_tenant(self, tenant_id: str) -> Tenant | None: ...

    @abc.abstractmethod
    async def list_tenants(
        self,
        *,
        property_id: str | None = None,
        status: TenantStatus | None = None,
    ) -> list[Tenant]: ...

    @abc.abstractmethod
    async def upsert_tenant(self, tenant: Tenant) -> None: ...

    # -- Maintenance --
    @abc.abstractmethod
    async def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None: ...

    @abc.abstractmethod
    async def list_maintenance_requests(
        self,
        *,
        property_id: str | None = None,
        unit_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]: ...

    @abc.abstractmethod
    async def upsert_maintenance_request(self, request: MaintenanceRequest) -> None: ...
