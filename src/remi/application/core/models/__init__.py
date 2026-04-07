"""Property management domain models — the ontology of the business.

``ls models/`` reveals the ontology:

    enums.py        — shared vocabulary (statuses, categories, types)
    address.py      — Address
    date_range.py   — DateRange
    property.py     — Property
    unit.py         — Unit
    tenant.py       — Tenant
    lease.py        — Lease
    owner.py        — Owner
    manager.py      — PropertyManager
    vendor.py       — Vendor
    maintenance.py  — MaintenanceRequest
    financials.py   — BalanceObservation
    tracking.py     — ActionItem, Note, MeetingBrief
    documents.py    — Document

Every public name is re-exported here so callers use:
``from remi.application.core.models import Lease``

Repository protocols live in ``application.core.protocols``.
"""

from remi.application.core.models.address import Address
from remi.application.core.models.date_range import DateRange
from remi.application.core.models.documents import Document
from remi.application.core.models.enums import (
    ActionItemStatus,
    AssetClass,
    DocumentType,
    EntityType,
    ImportStatus,
    LeaseStatus,
    LeaseType,
    MaintenanceSource,
    MaintenanceStatus,
    NoteProvenance,
    OccupancyStatus,
    OwnerType,
    Platform,
    Priority,
    PropertyType,
    RenewalStatus,
    ReportScope,
    ReportType,
    TenantStatus,
    TradeCategory,
    UnitType,
)
from remi.application.core.models.financials import BalanceObservation
from remi.application.core.models.lease import Lease
from remi.application.core.models.maintenance import MaintenanceRequest
from remi.application.core.models.manager import PropertyManager
from remi.application.core.models.owner import Owner
from remi.application.core.models.property import Property
from remi.application.core.models.tenant import Tenant
from remi.application.core.models.tracking import (
    ActionItem,
    MeetingBrief,
    Note,
)
from remi.application.core.models.unit import Unit
from remi.application.core.models.vendor import Vendor

__all__ = [
    # Enums
    "ActionItemStatus",
    "AssetClass",
    "DocumentType",
    "EntityType",
    "ImportStatus",
    "LeaseStatus",
    "LeaseType",
    "MaintenanceSource",
    "MaintenanceStatus",
    "NoteProvenance",
    "OccupancyStatus",
    "OwnerType",
    "Platform",
    "Priority",
    "PropertyType",
    "RenewalStatus",
    "ReportScope",
    "ReportType",
    "TenantStatus",
    "TradeCategory",
    "UnitType",
    # Physical
    "Address",
    "DateRange",
    "Property",
    "Unit",
    # People
    "Tenant",
    "Owner",
    "PropertyManager",
    # Contracts
    "Lease",
    # Financials
    "BalanceObservation",
    # Operations
    "MaintenanceRequest",
    "Vendor",
    # Documents
    "Document",
    # Tracking
    "ActionItem",
    "MeetingBrief",
    "Note",
]
