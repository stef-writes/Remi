"""Property management domain models — the ontology of the business.

``ls models/`` reveals the ontology:

    enums.py        — shared vocabulary (statuses, categories, types)
    oversight.py    — who's responsible (Owner, PropertyManager, Portfolio)
    assets.py       — the physical book (Address, Property, Unit)
    leasing.py      — who's in them, on what terms (Tenant, Lease)
    operations.py   — the work (Vendor, MaintenanceRequest)
    tracking.py     — director follow-up (ActionItem)

Every public name is re-exported here so existing imports continue to
work: ``from remi.domain.portfolio.models import Lease`` resolves
identically whether the caller knows about the submodules or not.

Repository protocols live in ``portfolio.protocols``.
"""

from remi.domain.portfolio.models.enums import (
    ActionItemPriority,
    ActionItemStatus,
    AssetClass,
    EntityType,
    LeaseStatus,
    LeaseType,
    MaintenanceCategory,
    MaintenanceSource,
    MaintenanceStatus,
    OccupancyStatus,
    Priority,
    PropertyType,
    RenewalStatus,
    TenantStatus,
    UnitStatus,
    UnitType,
    VendorCategory,
)
from remi.domain.portfolio.models.oversight import (
    Owner,
    Portfolio,
    PropertyManager,
)
from remi.domain.portfolio.models.assets import (
    Address,
    Property,
    Unit,
)
from remi.domain.portfolio.models.leasing import (
    Lease,
    Tenant,
)
from remi.domain.portfolio.models.operations import (
    MaintenanceRequest,
    Vendor,
)
from remi.domain.portfolio.models.tracking import (
    ActionItem,
)

__all__ = [
    # Enums
    "ActionItemPriority",
    "ActionItemStatus",
    "AssetClass",
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
    # Tracking
    "ActionItem",
]
