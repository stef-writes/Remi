"""Narrow repository protocols — one per entity group.

New code should depend on the narrowest protocol it actually needs.
``PropertyStore`` is a composite that inherits every protocol for
backward compatibility.

Infrastructure ports (KnowledgeWriter, etc.) decouple
``application/services/`` from ``agent/`` primitives.  Implementations
live in ``application/infra/``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

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
from remi.types.result import WriteResult


class ManagerRepository(abc.ABC):
    @abc.abstractmethod
    async def get_manager(self, manager_id: str) -> PropertyManager | None: ...

    @abc.abstractmethod
    async def list_managers(self) -> list[PropertyManager]: ...

    @abc.abstractmethod
    async def upsert_manager(self, manager: PropertyManager) -> WriteResult[PropertyManager]: ...

    @abc.abstractmethod
    async def delete_manager(self, manager_id: str) -> bool: ...


class PortfolioRepository(abc.ABC):
    @abc.abstractmethod
    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None: ...

    @abc.abstractmethod
    async def list_portfolios(self, *, manager_id: str | None = None) -> list[Portfolio]: ...

    @abc.abstractmethod
    async def upsert_portfolio(self, portfolio: Portfolio) -> WriteResult[Portfolio]: ...


class PropertyRepository(abc.ABC):
    @abc.abstractmethod
    async def get_property(self, property_id: str) -> Property | None: ...

    @abc.abstractmethod
    async def list_properties(self, *, portfolio_id: str | None = None) -> list[Property]: ...

    @abc.abstractmethod
    async def upsert_property(self, prop: Property) -> WriteResult[Property]: ...

    @abc.abstractmethod
    async def delete_property(self, property_id: str) -> bool: ...


class UnitRepository(abc.ABC):
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
    async def upsert_unit(self, unit: Unit) -> WriteResult[Unit]: ...

    @abc.abstractmethod
    async def delete_units_by_property(self, property_id: str) -> int:
        """Remove all units for a property. Returns count deleted."""
        ...


class LeaseRepository(abc.ABC):
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
    async def upsert_lease(self, lease: Lease) -> WriteResult[Lease]: ...

    @abc.abstractmethod
    async def delete_leases_by_property(self, property_id: str) -> int:
        """Remove all leases for a property. Returns count deleted."""
        ...


class TenantRepository(abc.ABC):
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
    async def upsert_tenant(self, tenant: Tenant) -> WriteResult[Tenant]: ...

    @abc.abstractmethod
    async def delete_tenant(self, tenant_id: str) -> bool: ...


class MaintenanceRepository(abc.ABC):
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
    async def upsert_maintenance_request(
        self,
        request: MaintenanceRequest,
    ) -> WriteResult[MaintenanceRequest]: ...


class ActionItemRepository(abc.ABC):
    @abc.abstractmethod
    async def get_action_item(self, item_id: str) -> ActionItem | None: ...

    @abc.abstractmethod
    async def list_action_items(
        self,
        *,
        manager_id: str | None = None,
        property_id: str | None = None,
        tenant_id: str | None = None,
        status: ActionItemStatus | None = None,
    ) -> list[ActionItem]: ...

    @abc.abstractmethod
    async def upsert_action_item(self, item: ActionItem) -> WriteResult[ActionItem]: ...

    @abc.abstractmethod
    async def delete_action_item(self, item_id: str) -> bool: ...


class OwnerRepository(abc.ABC):
    @abc.abstractmethod
    async def get_owner(self, owner_id: str) -> Owner | None: ...

    @abc.abstractmethod
    async def list_owners(self) -> list[Owner]: ...

    @abc.abstractmethod
    async def upsert_owner(self, owner: Owner) -> WriteResult[Owner]: ...

    @abc.abstractmethod
    async def delete_owner(self, owner_id: str) -> bool: ...


class VendorRepository(abc.ABC):
    @abc.abstractmethod
    async def get_vendor(self, vendor_id: str) -> Vendor | None: ...

    @abc.abstractmethod
    async def list_vendors(
        self,
        *,
        category: VendorCategory | None = None,
        is_internal: bool | None = None,
    ) -> list[Vendor]: ...

    @abc.abstractmethod
    async def upsert_vendor(self, vendor: Vendor) -> WriteResult[Vendor]: ...

    @abc.abstractmethod
    async def delete_vendor(self, vendor_id: str) -> bool: ...


class NoteRepository(abc.ABC):
    @abc.abstractmethod
    async def get_note(self, note_id: str) -> Note | None: ...

    @abc.abstractmethod
    async def list_notes(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        provenance: NoteProvenance | None = None,
    ) -> list[Note]: ...

    @abc.abstractmethod
    async def upsert_note(self, note: Note) -> WriteResult[Note]: ...

    @abc.abstractmethod
    async def delete_note(self, note_id: str) -> bool: ...


class DocumentRepository(abc.ABC):
    @abc.abstractmethod
    async def get_document(self, doc_id: str) -> Document | None: ...

    @abc.abstractmethod
    async def list_documents(
        self,
        *,
        unit_id: str | None = None,
        property_id: str | None = None,
        manager_id: str | None = None,
        lease_id: str | None = None,
        document_type: DocumentType | None = None,
    ) -> list[Document]: ...

    @abc.abstractmethod
    async def upsert_document(self, doc: Document) -> WriteResult[Document]: ...

    @abc.abstractmethod
    async def delete_document(self, doc_id: str) -> bool: ...


class PropertyStore(
    OwnerRepository,
    ManagerRepository,
    PortfolioRepository,
    PropertyRepository,
    UnitRepository,
    LeaseRepository,
    TenantRepository,
    MaintenanceRepository,
    VendorRepository,
    ActionItemRepository,
    NoteRepository,
    DocumentRepository,
):
    """Full property store — prefer narrow per-entity protocols in new code."""

    pass


# ---------------------------------------------------------------------------
# Infrastructure ports — decouple services from agent/ primitives
# ---------------------------------------------------------------------------


@dataclass
class KBEntity:
    """Application-level representation of a knowledge-graph entity."""

    entity_id: str
    entity_type: str
    namespace: str
    properties: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KBRelationship:
    """Application-level representation of a knowledge-graph relationship."""

    source_id: str
    target_id: str
    relation_type: str
    namespace: str


class KnowledgeWriter(abc.ABC):
    """Port for writing entities and relationships to the knowledge graph.

    Hides agent.graph.KnowledgeStore from application services that only
    need to persist extracted knowledge (ingestion, apply, etc.).
    """

    @abc.abstractmethod
    async def put_entity(self, entity: KBEntity) -> None: ...

    @abc.abstractmethod
    async def get_entity(self, namespace: str, entity_id: str) -> KBEntity | None: ...

    @abc.abstractmethod
    async def put_relationship(self, rel: KBRelationship) -> None: ...


class KnowledgeReader(abc.ABC):
    """Port for reading knowledge-graph data from application services.

    Provides the narrow query surface that dashboard, auto-assign, and
    search need — without exposing the full KnowledgeStore API.
    """

    @abc.abstractmethod
    async def find_entities(
        self,
        namespace: str,
        entity_type: str | None = None,
        *,
        limit: int = 20,
    ) -> list[KBEntity]: ...

    @abc.abstractmethod
    async def list_namespaces(self) -> list[str]: ...


@dataclass
class EmbedRequest:
    """Application-level embedding request — what text to embed for which entity."""

    id: str
    text: str
    source_entity_id: str
    source_entity_type: str
    source_field: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextSearchHit:
    """A single result from vector search."""

    entity_id: str
    entity_type: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class TextIndexer(abc.ABC):
    """Port for embedding and storing text vectors.

    Collapses Embedder + VectorStore into a single service boundary
    for application code that just needs "embed this text, store it."
    """

    @abc.abstractmethod
    async def index_many(self, requests: list[EmbedRequest]) -> int:
        """Embed and store. Returns count successfully indexed."""
        ...


class VectorSearch(abc.ABC):
    """Port for keyword + semantic search over the vector index."""

    @abc.abstractmethod
    async def keyword_search(
        self,
        query: str,
        *,
        fields: list[str] | None = None,
        limit: int = 10,
    ) -> list[TextSearchHit]: ...

    @abc.abstractmethod
    async def semantic_search(
        self,
        query: str,
        *,
        limit: int = 10,
        min_score: float = 0.0,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[TextSearchHit]: ...
