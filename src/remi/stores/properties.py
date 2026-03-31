"""In-memory implementation of PropertyStore."""

from __future__ import annotations

from pydantic import BaseModel

from remi.models.properties import (
    ActionItem,
    ActionItemStatus,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    MaintenanceStatus,
    OccupancyStatus,
    Portfolio,
    Property,
    PropertyManager,
    PropertyStore,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)


def _merge(existing: BaseModel, incoming: BaseModel) -> BaseModel:
    """Merge incoming fields into existing, preserving existing values only
    for fields that were *not explicitly set* on the incoming model.

    Uses Pydantic's ``model_fields_set`` to distinguish "explicitly passed
    Decimal('0')" from "defaulted to Decimal('0')" — critical for correctly
    handling week-over-week report uploads where a tenant may have paid off
    their balance or a unit may have gone vacant.
    """
    explicitly_set = incoming.model_fields_set
    if not explicitly_set:
        return existing
    incoming_data = {name: getattr(incoming, name) for name in explicitly_set}
    return existing.model_copy(update=incoming_data)


class InMemoryPropertyStore(PropertyStore):
    def __init__(self) -> None:
        self._managers: dict[str, PropertyManager] = {}
        self._portfolios: dict[str, Portfolio] = {}
        self._properties: dict[str, Property] = {}
        self._units: dict[str, Unit] = {}
        self._leases: dict[str, Lease] = {}
        self._tenants: dict[str, Tenant] = {}
        self._maintenance: dict[str, MaintenanceRequest] = {}
        self._action_items: dict[str, ActionItem] = {}

    # -- PropertyManager --
    async def get_manager(self, manager_id: str) -> PropertyManager | None:
        return self._managers.get(manager_id)

    async def list_managers(self) -> list[PropertyManager]:
        return list(self._managers.values())

    async def upsert_manager(self, manager: PropertyManager) -> None:
        existing = self._managers.get(manager.id)
        self._managers[manager.id] = _merge(existing, manager) if existing else manager  # type: ignore[assignment]

    # -- Portfolio --
    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        return self._portfolios.get(portfolio_id)

    async def list_portfolios(self, *, manager_id: str | None = None) -> list[Portfolio]:
        items = list(self._portfolios.values())
        if manager_id:
            items = [p for p in items if p.manager_id == manager_id]
        return items

    async def upsert_portfolio(self, portfolio: Portfolio) -> None:
        existing = self._portfolios.get(portfolio.id)
        self._portfolios[portfolio.id] = _merge(existing, portfolio) if existing else portfolio  # type: ignore[assignment]

    # -- Property --
    async def get_property(self, property_id: str) -> Property | None:
        return self._properties.get(property_id)

    async def list_properties(self, *, portfolio_id: str | None = None) -> list[Property]:
        items = list(self._properties.values())
        if portfolio_id:
            items = [p for p in items if p.portfolio_id == portfolio_id]
        return items

    async def upsert_property(self, prop: Property) -> None:
        existing = self._properties.get(prop.id)
        self._properties[prop.id] = _merge(existing, prop) if existing else prop  # type: ignore[assignment]

    # -- Unit --
    async def get_unit(self, unit_id: str) -> Unit | None:
        return self._units.get(unit_id)

    async def list_units(
        self,
        *,
        property_id: str | None = None,
        status: UnitStatus | None = None,
        occupancy_status: OccupancyStatus | None = None,
    ) -> list[Unit]:
        items = list(self._units.values())
        if property_id:
            items = [u for u in items if u.property_id == property_id]
        if status:
            items = [u for u in items if u.status == status]
        if occupancy_status:
            items = [u for u in items if u.occupancy_status == occupancy_status]
        return items

    async def upsert_unit(self, unit: Unit) -> None:
        existing = self._units.get(unit.id)
        self._units[unit.id] = _merge(existing, unit) if existing else unit  # type: ignore[assignment]

    # -- Lease --
    async def get_lease(self, lease_id: str) -> Lease | None:
        return self._leases.get(lease_id)

    async def list_leases(
        self,
        *,
        unit_id: str | None = None,
        tenant_id: str | None = None,
        property_id: str | None = None,
        status: LeaseStatus | None = None,
    ) -> list[Lease]:
        items = list(self._leases.values())
        if unit_id:
            items = [le for le in items if le.unit_id == unit_id]
        if tenant_id:
            items = [le for le in items if le.tenant_id == tenant_id]
        if property_id:
            items = [le for le in items if le.property_id == property_id]
        if status:
            items = [le for le in items if le.status == status]
        return items

    async def upsert_lease(self, lease: Lease) -> None:
        existing = self._leases.get(lease.id)
        self._leases[lease.id] = _merge(existing, lease) if existing else lease  # type: ignore[assignment]

    # -- Tenant --
    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    async def list_tenants(
        self,
        *,
        property_id: str | None = None,
        status: TenantStatus | None = None,
    ) -> list[Tenant]:
        items = list(self._tenants.values())
        if property_id:
            leases = [le for le in self._leases.values() if le.property_id == property_id]
            tenant_ids = {le.tenant_id for le in leases}
            items = [t for t in items if t.id in tenant_ids]
        if status:
            items = [t for t in items if t.status == status]
        return items

    async def upsert_tenant(self, tenant: Tenant) -> None:
        existing = self._tenants.get(tenant.id)
        self._tenants[tenant.id] = _merge(existing, tenant) if existing else tenant  # type: ignore[assignment]

    # -- Maintenance --
    async def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None:
        return self._maintenance.get(request_id)

    async def list_maintenance_requests(
        self,
        *,
        property_id: str | None = None,
        unit_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]:
        items = list(self._maintenance.values())
        if property_id:
            items = [mr for mr in items if mr.property_id == property_id]
        if unit_id:
            items = [mr for mr in items if mr.unit_id == unit_id]
        if status:
            items = [mr for mr in items if mr.status == status]
        return items

    async def upsert_maintenance_request(self, request: MaintenanceRequest) -> None:
        existing = self._maintenance.get(request.id)
        self._maintenance[request.id] = _merge(existing, request) if existing else request  # type: ignore[assignment]

    # -- Deletes --
    async def delete_manager(self, manager_id: str) -> bool:
        if manager_id not in self._managers:
            return False
        del self._managers[manager_id]
        pf_ids = [p.id for p in self._portfolios.values() if p.manager_id == manager_id]
        for pf_id in pf_ids:
            del self._portfolios[pf_id]
        for prop in list(self._properties.values()):
            if prop.portfolio_id in pf_ids:
                self._properties[prop.id] = prop.model_copy(update={"portfolio_id": ""})
        return True

    async def delete_property(self, property_id: str) -> bool:
        if property_id not in self._properties:
            return False
        del self._properties[property_id]
        unit_ids = [u.id for u in self._units.values() if u.property_id == property_id]
        for uid in unit_ids:
            del self._units[uid]
        lease_ids = [le.id for le in self._leases.values() if le.property_id == property_id]
        for lid in lease_ids:
            del self._leases[lid]
        return True

    async def delete_tenant(self, tenant_id: str) -> bool:
        if tenant_id not in self._tenants:
            return False
        del self._tenants[tenant_id]
        lease_ids = [le.id for le in self._leases.values() if le.tenant_id == tenant_id]
        for lid in lease_ids:
            del self._leases[lid]
        return True

    # -- Action Items --
    async def get_action_item(self, item_id: str) -> ActionItem | None:
        return self._action_items.get(item_id)

    async def list_action_items(
        self,
        *,
        manager_id: str | None = None,
        property_id: str | None = None,
        tenant_id: str | None = None,
        status: ActionItemStatus | None = None,
    ) -> list[ActionItem]:
        items = list(self._action_items.values())
        if manager_id:
            items = [i for i in items if i.manager_id == manager_id]
        if property_id:
            items = [i for i in items if i.property_id == property_id]
        if tenant_id:
            items = [i for i in items if i.tenant_id == tenant_id]
        if status:
            items = [i for i in items if i.status == status]
        return items

    async def upsert_action_item(self, item: ActionItem) -> None:
        existing = self._action_items.get(item.id)
        self._action_items[item.id] = _merge(existing, item) if existing else item  # type: ignore[assignment]

    async def delete_action_item(self, item_id: str) -> bool:
        return self._action_items.pop(item_id, None) is not None
