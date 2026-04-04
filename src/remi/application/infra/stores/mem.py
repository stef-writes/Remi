"""In-memory implementation of PropertyStore."""

from __future__ import annotations

from pydantic import BaseModel

from remi.application.core.models import (
    ActionItem,
    ActionItemStatus,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    MaintenanceStatus,
    Note,
    NoteProvenance,
    OccupancyStatus,
    Owner,
    Portfolio,
    Property,
    PropertyManager,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
    Vendor,
    VendorCategory,
)
from remi.application.core.protocols import PropertyStore
from remi.types.result import WriteOutcome, WriteResult


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


_COLLECTION_MODELS: dict[str, type[BaseModel]] = {
    "owners": Owner,
    "managers": PropertyManager,
    "portfolios": Portfolio,
    "properties": Property,
    "units": Unit,
    "leases": Lease,
    "tenants": Tenant,
    "maintenance": MaintenanceRequest,
    "vendors": Vendor,
    "action_items": ActionItem,
    "notes": Note,
}


class InMemoryPropertyStore(PropertyStore):
    def __init__(self) -> None:
        self._owners: dict[str, Owner] = {}
        self._managers: dict[str, PropertyManager] = {}
        self._portfolios: dict[str, Portfolio] = {}
        self._properties: dict[str, Property] = {}
        self._units: dict[str, Unit] = {}
        self._leases: dict[str, Lease] = {}
        self._tenants: dict[str, Tenant] = {}
        self._maintenance: dict[str, MaintenanceRequest] = {}
        self._vendors: dict[str, Vendor] = {}
        self._action_items: dict[str, ActionItem] = {}
        self._notes: dict[str, Note] = {}

    def dump_state(self) -> dict[str, list[dict[str, object]]]:
        """Serialize all collections for snapshot cache."""
        collections = {
            "owners": self._owners,
            "managers": self._managers,
            "portfolios": self._portfolios,
            "properties": self._properties,
            "units": self._units,
            "leases": self._leases,
            "tenants": self._tenants,
            "maintenance": self._maintenance,
            "vendors": self._vendors,
            "action_items": self._action_items,
            "notes": self._notes,
        }
        return {
            name: [v.model_dump(mode="json") for v in coll.values()]
            for name, coll in collections.items()
        }

    def load_state(self, data: dict[str, list[dict[str, object]]]) -> None:
        """Restore all collections from a previously dumped snapshot."""
        attr_map: dict[str, dict[str, BaseModel]] = {
            "owners": self._owners,
            "managers": self._managers,
            "portfolios": self._portfolios,
            "properties": self._properties,
            "units": self._units,
            "leases": self._leases,
            "tenants": self._tenants,
            "maintenance": self._maintenance,
            "vendors": self._vendors,
            "action_items": self._action_items,
            "notes": self._notes,
        }
        for name, raw_items in data.items():
            model_cls = _COLLECTION_MODELS.get(name)
            coll = attr_map.get(name)
            if model_cls is None or coll is None:
                continue
            coll.clear()
            for raw in raw_items:
                obj = model_cls.model_validate(raw)
                coll[obj.id] = obj  # type: ignore[attr-defined]

    # -- Owner --
    async def get_owner(self, owner_id: str) -> Owner | None:
        return self._owners.get(owner_id)

    async def list_owners(self) -> list[Owner]:
        return list(self._owners.values())

    async def upsert_owner(self, owner: Owner) -> WriteResult[Owner]:
        existing = self._owners.get(owner.id)
        if existing:
            merged: Owner = _merge(existing, owner)  # type: ignore[assignment]
            self._owners[owner.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._owners[owner.id] = owner
        return WriteResult(entity=owner, outcome=WriteOutcome.CREATED)

    async def delete_owner(self, owner_id: str) -> bool:
        return self._owners.pop(owner_id, None) is not None

    # -- PropertyManager --
    async def get_manager(self, manager_id: str) -> PropertyManager | None:
        return self._managers.get(manager_id)

    async def list_managers(self) -> list[PropertyManager]:
        return list(self._managers.values())

    async def upsert_manager(self, manager: PropertyManager) -> WriteResult[PropertyManager]:
        existing = self._managers.get(manager.id)
        if existing:
            merged: PropertyManager = _merge(existing, manager)  # type: ignore[assignment]
            self._managers[manager.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._managers[manager.id] = manager
        return WriteResult(entity=manager, outcome=WriteOutcome.CREATED)

    # -- Portfolio --
    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        return self._portfolios.get(portfolio_id)

    async def list_portfolios(self, *, manager_id: str | None = None) -> list[Portfolio]:
        items = list(self._portfolios.values())
        if manager_id:
            items = [p for p in items if p.manager_id == manager_id]
        return items

    async def upsert_portfolio(self, portfolio: Portfolio) -> WriteResult[Portfolio]:
        existing = self._portfolios.get(portfolio.id)
        if existing:
            merged: Portfolio = _merge(existing, portfolio)  # type: ignore[assignment]
            self._portfolios[portfolio.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._portfolios[portfolio.id] = portfolio
        return WriteResult(entity=portfolio, outcome=WriteOutcome.CREATED)

    # -- Property --
    async def get_property(self, property_id: str) -> Property | None:
        return self._properties.get(property_id)

    async def list_properties(self, *, portfolio_id: str | None = None) -> list[Property]:
        items = list(self._properties.values())
        if portfolio_id:
            items = [p for p in items if p.portfolio_id == portfolio_id]
        return items

    async def upsert_property(self, prop: Property) -> WriteResult[Property]:
        existing = self._properties.get(prop.id)
        if existing:
            merged: Property = _merge(existing, prop)  # type: ignore[assignment]
            self._properties[prop.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._properties[prop.id] = prop
        return WriteResult(entity=prop, outcome=WriteOutcome.CREATED)

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

    async def upsert_unit(self, unit: Unit) -> WriteResult[Unit]:
        existing = self._units.get(unit.id)
        if existing:
            merged: Unit = _merge(existing, unit)  # type: ignore[assignment]
            self._units[unit.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._units[unit.id] = unit
        return WriteResult(entity=unit, outcome=WriteOutcome.CREATED)

    async def delete_units_by_property(self, property_id: str) -> int:
        ids = [u.id for u in self._units.values() if u.property_id == property_id]
        for uid in ids:
            del self._units[uid]
        return len(ids)

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

    async def upsert_lease(self, lease: Lease) -> WriteResult[Lease]:
        existing = self._leases.get(lease.id)
        if existing:
            merged: Lease = _merge(existing, lease)  # type: ignore[assignment]
            self._leases[lease.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._leases[lease.id] = lease
        return WriteResult(entity=lease, outcome=WriteOutcome.CREATED)

    async def delete_leases_by_property(self, property_id: str) -> int:
        ids = [le.id for le in self._leases.values() if le.property_id == property_id]
        for lid in ids:
            del self._leases[lid]
        return len(ids)

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

    async def upsert_tenant(self, tenant: Tenant) -> WriteResult[Tenant]:
        existing = self._tenants.get(tenant.id)
        if existing:
            merged: Tenant = _merge(existing, tenant)  # type: ignore[assignment]
            self._tenants[tenant.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._tenants[tenant.id] = tenant
        return WriteResult(entity=tenant, outcome=WriteOutcome.CREATED)

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

    async def upsert_maintenance_request(
        self,
        request: MaintenanceRequest,
    ) -> WriteResult[MaintenanceRequest]:
        existing = self._maintenance.get(request.id)
        if existing:
            merged: MaintenanceRequest = _merge(existing, request)  # type: ignore[assignment]
            self._maintenance[request.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._maintenance[request.id] = request
        return WriteResult(entity=request, outcome=WriteOutcome.CREATED)

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

    # -- Vendor --
    async def get_vendor(self, vendor_id: str) -> Vendor | None:
        return self._vendors.get(vendor_id)

    async def list_vendors(
        self,
        *,
        category: VendorCategory | None = None,
        is_internal: bool | None = None,
    ) -> list[Vendor]:
        items = list(self._vendors.values())
        if category:
            items = [v for v in items if v.category == category]
        if is_internal is not None:
            items = [v for v in items if v.is_internal == is_internal]
        return items

    async def upsert_vendor(self, vendor: Vendor) -> WriteResult[Vendor]:
        existing = self._vendors.get(vendor.id)
        if existing:
            merged: Vendor = _merge(existing, vendor)  # type: ignore[assignment]
            self._vendors[vendor.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._vendors[vendor.id] = vendor
        return WriteResult(entity=vendor, outcome=WriteOutcome.CREATED)

    async def delete_vendor(self, vendor_id: str) -> bool:
        return self._vendors.pop(vendor_id, None) is not None

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

    async def upsert_action_item(self, item: ActionItem) -> WriteResult[ActionItem]:
        existing = self._action_items.get(item.id)
        if existing:
            merged: ActionItem = _merge(existing, item)  # type: ignore[assignment]
            self._action_items[item.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._action_items[item.id] = item
        return WriteResult(entity=item, outcome=WriteOutcome.CREATED)

    async def delete_action_item(self, item_id: str) -> bool:
        return self._action_items.pop(item_id, None) is not None

    # -- Notes --
    async def get_note(self, note_id: str) -> Note | None:
        return self._notes.get(note_id)

    async def list_notes(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        provenance: NoteProvenance | None = None,
    ) -> list[Note]:
        notes = list(self._notes.values())
        if entity_type:
            notes = [n for n in notes if n.entity_type == entity_type]
        if entity_id:
            notes = [n for n in notes if n.entity_id == entity_id]
        if provenance:
            notes = [n for n in notes if n.provenance == provenance]
        return notes

    async def upsert_note(self, note: Note) -> WriteResult[Note]:
        existing = self._notes.get(note.id)
        if existing:
            merged: Note = _merge(existing, note)  # type: ignore[assignment]
            self._notes[note.id] = merged
            outcome = WriteOutcome.NOOP if merged == existing else WriteOutcome.UPDATED
            return WriteResult(entity=merged, outcome=outcome)
        self._notes[note.id] = note
        return WriteResult(entity=note, outcome=WriteOutcome.CREATED)

    async def delete_note(self, note_id: str) -> bool:
        return self._notes.pop(note_id, None) is not None
