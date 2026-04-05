"""Property management domain models — the ontology of the business.

``ls models/`` reveals the ontology:

    enums.py        — shared vocabulary (statuses, categories, types)
    oversight.py    — who's responsible (Owner, PropertyManager, Portfolio)
    assets.py       — the physical book (Address, Property, Unit)
    leasing.py      — who's in them, on what terms (Tenant, Lease)
    operations.py   — the work (Vendor, MaintenanceRequest)
    tracking.py     — director follow-up (ActionItem, Note)
    documents.py    — uploaded files scoped to domain entities (Document)

Every public name is re-exported here so existing imports continue to
work: ``from remi.application.core.models import Lease`` resolves
identically whether the caller knows about the submodules or not.

Repository protocols live in ``application.core.protocols``.
"""

from remi.application.core.models.assets import (
    Address,
    Property,
    Unit,
)
from remi.application.core.models.documents import Document
from remi.application.core.models.enums import (
    ActionItemPriority,
    ActionItemStatus,
    AssetClass,
    DocumentType,
    EntityType,
    LeaseStatus,
    LeaseType,
    MaintenanceCategory,
    MaintenanceSource,
    MaintenanceStatus,
    NoteProvenance,
    OccupancyStatus,
    Priority,
    PropertyType,
    RenewalStatus,
    TenantStatus,
    UnitStatus,
    UnitType,
    VendorCategory,
)
from remi.application.core.models.leasing import (
    Lease,
    Tenant,
)
from remi.application.core.models.operations import (
    MaintenanceRequest,
    Vendor,
)
from remi.application.core.models.oversight import (
    Owner,
    Portfolio,
    PropertyManager,
)
from remi.application.core.models.tracking import (
    ActionItem,
    Note,
)

__all__ = [
    # Enums
    "ActionItemPriority",
    "ActionItemStatus",
    "AssetClass",
    "DocumentType",
    "EntityType",
    "LeaseStatus",
    "LeaseType",
    "MaintenanceCategory",
    "MaintenanceSource",
    "MaintenanceStatus",
    "OccupancyStatus",
    "Priority",
    "PropertyType",
    "RenewalStatus",
    "TenantStatus",
    "UnitStatus",
    "UnitType",
    "VendorCategory",
    # Oversight
    "Owner",
    "Portfolio",
    "PropertyManager",
    # Assets
    "Address",
    "Property",
    "Unit",
    # Leasing
    "Lease",
    "Tenant",
    # Operations
    "MaintenanceRequest",
    "Vendor",
    # Documents
    "Document",
    # Tracking
    "ActionItem",
    "Note",
    "NoteProvenance",
]
