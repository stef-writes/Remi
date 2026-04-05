"""ProjectingPropertyStore — decorator that auto-projects FK edges after each upsert.

Wraps any PropertyStore and calls GraphProjector.project_entity after every
successful upsert, keeping the knowledge graph live without coupling the
store implementations to the graph layer.

All read, list, and delete calls delegate to the inner store unchanged.
"""

from __future__ import annotations

import structlog

from remi.agent.graph import GraphProjector
from remi.application.core.models import (
    ActionItem,
    ActionItemStatus,
    Document,
    DocumentType,
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
from remi.types.result import WriteResult

_log = structlog.get_logger(__name__)


class ProjectingPropertyStore(PropertyStore):
    """PropertyStore decorator — projects graph edges after every upsert."""

    def __init__(self, inner: PropertyStore, projector: GraphProjector) -> None:
        self._inner = inner
        self._projector = projector

    async def _project(self, entity_type: str, entity_id: str, data: dict[str, object]) -> None:
        try:
            await self._projector.project_entity(entity_type, entity_id, data)
        except Exception:
            _log.warning(
                "auto_projection_failed",
                entity_type=entity_type,
                entity_id=entity_id,
                exc_info=True,
            )

    # -- Managers -------------------------------------------------------------

    async def get_manager(self, manager_id: str) -> PropertyManager | None:
        return await self._inner.get_manager(manager_id)

    async def list_managers(self) -> list[PropertyManager]:
        return await self._inner.list_managers()

    async def upsert_manager(self, manager: PropertyManager) -> WriteResult[PropertyManager]:
        result = await self._inner.upsert_manager(manager)
        await self._project("PropertyManager", manager.id, manager.model_dump(mode="json"))
        return result

    async def delete_manager(self, manager_id: str) -> bool:
        return await self._inner.delete_manager(manager_id)

    # -- Portfolios -----------------------------------------------------------

    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        return await self._inner.get_portfolio(portfolio_id)

    async def list_portfolios(self, *, manager_id: str | None = None) -> list[Portfolio]:
        return await self._inner.list_portfolios(manager_id=manager_id)

    async def upsert_portfolio(self, portfolio: Portfolio) -> WriteResult[Portfolio]:
        result = await self._inner.upsert_portfolio(portfolio)
        await self._project("Portfolio", portfolio.id, portfolio.model_dump(mode="json"))
        return result

    # -- Properties -----------------------------------------------------------

    async def get_property(self, property_id: str) -> Property | None:
        return await self._inner.get_property(property_id)

    async def list_properties(self, *, portfolio_id: str | None = None) -> list[Property]:
        return await self._inner.list_properties(portfolio_id=portfolio_id)

    async def upsert_property(self, prop: Property) -> WriteResult[Property]:
        result = await self._inner.upsert_property(prop)
        await self._project("Property", prop.id, prop.model_dump(mode="json"))
        return result

    async def delete_property(self, property_id: str) -> bool:
        return await self._inner.delete_property(property_id)

    # -- Units ----------------------------------------------------------------

    async def get_unit(self, unit_id: str) -> Unit | None:
        return await self._inner.get_unit(unit_id)

    async def list_units(
        self,
        *,
        property_id: str | None = None,
        status: UnitStatus | None = None,
        occupancy_status: OccupancyStatus | None = None,
    ) -> list[Unit]:
        return await self._inner.list_units(
            property_id=property_id,
            status=status,
            occupancy_status=occupancy_status,
        )

    async def upsert_unit(self, unit: Unit) -> WriteResult[Unit]:
        result = await self._inner.upsert_unit(unit)
        await self._project("Unit", unit.id, unit.model_dump(mode="json"))
        return result

    async def delete_units_by_property(self, property_id: str) -> int:
        return await self._inner.delete_units_by_property(property_id)

    # -- Leases ---------------------------------------------------------------

    async def get_lease(self, lease_id: str) -> Lease | None:
        return await self._inner.get_lease(lease_id)

    async def list_leases(
        self,
        *,
        unit_id: str | None = None,
        tenant_id: str | None = None,
        property_id: str | None = None,
        status: LeaseStatus | None = None,
    ) -> list[Lease]:
        return await self._inner.list_leases(
            unit_id=unit_id,
            tenant_id=tenant_id,
            property_id=property_id,
            status=status,
        )

    async def upsert_lease(self, lease: Lease) -> WriteResult[Lease]:
        result = await self._inner.upsert_lease(lease)
        await self._project("Lease", lease.id, lease.model_dump(mode="json"))
        return result

    async def delete_leases_by_property(self, property_id: str) -> int:
        return await self._inner.delete_leases_by_property(property_id)

    # -- Tenants --------------------------------------------------------------

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        return await self._inner.get_tenant(tenant_id)

    async def list_tenants(
        self,
        *,
        property_id: str | None = None,
        status: TenantStatus | None = None,
    ) -> list[Tenant]:
        return await self._inner.list_tenants(property_id=property_id, status=status)

    async def upsert_tenant(self, tenant: Tenant) -> WriteResult[Tenant]:
        result = await self._inner.upsert_tenant(tenant)
        await self._project("Tenant", tenant.id, tenant.model_dump(mode="json"))
        return result

    async def delete_tenant(self, tenant_id: str) -> bool:
        return await self._inner.delete_tenant(tenant_id)

    # -- Maintenance ----------------------------------------------------------

    async def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None:
        return await self._inner.get_maintenance_request(request_id)

    async def list_maintenance_requests(
        self,
        *,
        property_id: str | None = None,
        unit_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]:
        return await self._inner.list_maintenance_requests(
            property_id=property_id,
            unit_id=unit_id,
            status=status,
        )

    async def upsert_maintenance_request(
        self, request: MaintenanceRequest
    ) -> WriteResult[MaintenanceRequest]:
        result = await self._inner.upsert_maintenance_request(request)
        await self._project("MaintenanceRequest", request.id, request.model_dump(mode="json"))
        return result

    # -- Owners ---------------------------------------------------------------

    async def get_owner(self, owner_id: str) -> Owner | None:
        return await self._inner.get_owner(owner_id)

    async def list_owners(self) -> list[Owner]:
        return await self._inner.list_owners()

    async def upsert_owner(self, owner: Owner) -> WriteResult[Owner]:
        result = await self._inner.upsert_owner(owner)
        await self._project("Owner", owner.id, owner.model_dump(mode="json"))
        return result

    async def delete_owner(self, owner_id: str) -> bool:
        return await self._inner.delete_owner(owner_id)

    # -- Vendors --------------------------------------------------------------

    async def get_vendor(self, vendor_id: str) -> Vendor | None:
        return await self._inner.get_vendor(vendor_id)

    async def list_vendors(
        self,
        *,
        category: VendorCategory | None = None,
        is_internal: bool | None = None,
    ) -> list[Vendor]:
        return await self._inner.list_vendors(category=category, is_internal=is_internal)

    async def upsert_vendor(self, vendor: Vendor) -> WriteResult[Vendor]:
        result = await self._inner.upsert_vendor(vendor)
        await self._project("Vendor", vendor.id, vendor.model_dump(mode="json"))
        return result

    async def delete_vendor(self, vendor_id: str) -> bool:
        return await self._inner.delete_vendor(vendor_id)

    # -- Action Items ---------------------------------------------------------

    async def get_action_item(self, item_id: str) -> ActionItem | None:
        return await self._inner.get_action_item(item_id)

    async def list_action_items(
        self,
        *,
        manager_id: str | None = None,
        property_id: str | None = None,
        tenant_id: str | None = None,
        status: ActionItemStatus | None = None,
    ) -> list[ActionItem]:
        return await self._inner.list_action_items(
            manager_id=manager_id,
            property_id=property_id,
            tenant_id=tenant_id,
            status=status,
        )

    async def upsert_action_item(self, item: ActionItem) -> WriteResult[ActionItem]:
        result = await self._inner.upsert_action_item(item)
        await self._project("ActionItem", item.id, item.model_dump(mode="json"))
        return result

    async def delete_action_item(self, item_id: str) -> bool:
        return await self._inner.delete_action_item(item_id)

    # -- Notes ----------------------------------------------------------------

    async def get_note(self, note_id: str) -> Note | None:
        return await self._inner.get_note(note_id)

    async def list_notes(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        provenance: NoteProvenance | None = None,
    ) -> list[Note]:
        return await self._inner.list_notes(
            entity_type=entity_type,
            entity_id=entity_id,
            provenance=provenance,
        )

    async def upsert_note(self, note: Note) -> WriteResult[Note]:
        result = await self._inner.upsert_note(note)
        await self._project("Note", note.id, note.model_dump(mode="json"))
        return result

    async def delete_note(self, note_id: str) -> bool:
        return await self._inner.delete_note(note_id)

    # -- Documents ------------------------------------------------------------

    async def get_document(self, doc_id: str) -> Document | None:
        return await self._inner.get_document(doc_id)

    async def list_documents(
        self,
        *,
        unit_id: str | None = None,
        property_id: str | None = None,
        manager_id: str | None = None,
        lease_id: str | None = None,
        document_type: DocumentType | None = None,
    ) -> list[Document]:
        return await self._inner.list_documents(
            unit_id=unit_id,
            property_id=property_id,
            manager_id=manager_id,
            lease_id=lease_id,
            document_type=document_type,
        )

    async def upsert_document(self, doc: Document) -> WriteResult[Document]:
        result = await self._inner.upsert_document(doc)
        await self._project("Document", doc.id, doc.model_dump(mode="json"))
        return result

    async def delete_document(self, doc_id: str) -> bool:
        return await self._inner.delete_document(doc_id)
