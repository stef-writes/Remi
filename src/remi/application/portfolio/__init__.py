"""Portfolio — entity resolvers for the property management domain.

Each module owns the read-side logic for one entity type:

    managers.py       Manager aggregation and ranking
    properties.py     Property list and detail
    units.py          Cross-property unit queries
    leases.py         Lease list and expiring-lease queries
    maintenance.py    Maintenance list and summary
    portfolios.py     Portfolio list and summary
    dashboard.py      Composite dashboard views
    rent_roll.py      Detailed rent-roll assembly
    auto_assign.py    KB-tag-based property-to-manager assignment

Read-model types live in ``_models.py`` and are re-exported here.
"""

from ._models import (
    AutoAssignResult,
    DelinquencyBoard,
    DelinquentTenant,
    ExpiringLease,
    ExpiringLeaseItem,
    ExpiringLeasesResult,
    LeaseCalendar,
    LeaseInfo,
    LeaseInRentRoll,
    LeaseListItem,
    LeaseListResult,
    MaintenanceInRentRoll,
    MaintenanceItem,
    MaintenanceListResult,
    MaintenanceSummaryResult,
    ManagerOverview,
    ManagerRanking,
    ManagerSummary,
    NeedsManagerResult,
    PortfolioListItem,
    PortfolioOverview,
    PortfolioSummaryResult,
    PropertyDetail,
    PropertyDetailUnit,
    PropertyInPortfolio,
    PropertyListItem,
    PropertySummary,
    RentRollResult,
    RentRollRow,
    RentRollUnit,
    RentRollView,
    TenantDetail,
    TenantInRentRoll,
    UnassignedProperty,
    UnitIssue,
    UnitListItem,
    UnitListResult,
    VacancyTracker,
    VacantUnit,
)
from .auto_assign import AutoAssignService
from .dashboard import DashboardQueryService
from .documents import DocumentResolver
from .leases import LeaseResolver
from .maintenance import MaintenanceResolver
from .managers import ManagerReviewService
from .portfolios import PortfolioResolver
from .properties import PropertyResolver
from .rent_roll import RentRollService
from .signals import SignalDigest, SignalResolver
from .tenants import TenantResolver
from .units import UnitResolver

__all__ = [
    # Resolvers
    "LeaseResolver",
    "MaintenanceResolver",
    "ManagerReviewService",
    "PortfolioResolver",
    "PropertyResolver",
    "RentRollService",
    "SignalDigest",
    "SignalResolver",
    "TenantResolver",
    "UnitResolver",
    # Composite
    "AutoAssignService",
    "DashboardQueryService",
    "DocumentResolver",
    # Read-models
    "AutoAssignResult",
    "DelinquencyBoard",
    "DelinquentTenant",
    "ExpiringLease",
    "ExpiringLeaseItem",
    "ExpiringLeasesResult",
    "LeaseCalendar",
    "LeaseInfo",
    "LeaseInRentRoll",
    "LeaseListItem",
    "LeaseListResult",
    "MaintenanceInRentRoll",
    "MaintenanceItem",
    "MaintenanceListResult",
    "MaintenanceSummaryResult",
    "ManagerOverview",
    "ManagerRanking",
    "ManagerSummary",
    "NeedsManagerResult",
    "PortfolioListItem",
    "PortfolioOverview",
    "PortfolioSummaryResult",
    "PropertyDetail",
    "PropertyDetailUnit",
    "PropertyInPortfolio",
    "PropertyListItem",
    "PropertySummary",
    "RentRollResult",
    "RentRollRow",
    "RentRollUnit",
    "RentRollView",
    "TenantDetail",
    "TenantInRentRoll",
    "UnassignedProperty",
    "UnitIssue",
    "UnitListItem",
    "UnitListResult",
    "VacancyTracker",
    "VacantUnit",
]
