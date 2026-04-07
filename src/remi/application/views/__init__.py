"""Views — computed read-models over the property management domain.

Each module owns the read-side logic for one domain concern:

    managers.py       Manager aggregation and ranking
    properties.py     Property list, detail, and cross-property unit queries
    leases.py         Lease list, expiring-lease calendar, tenant detail
    maintenance.py    Maintenance list and summary
    dashboard.py      Composite dashboard views
    rent_roll.py      Detailed rent-roll assembly
Read-model types live in ``_models.py`` and are re-exported here.
"""

from ._models import (
    AutoAssignResult,
    DashboardOverview,
    DelinquencyBoard,
    DelinquencyTrend,
    DelinquentTenant,
    ExpiringLease,
    LeaseCalendar,
    LeaseInfo,
    LeaseInRentRoll,
    LeaseListItem,
    LeaseListResult,
    MaintenanceInRentRoll,
    MaintenanceItem,
    MaintenanceListResult,
    MaintenanceSummaryResult,
    MaintenanceTrend,
    MaintenanceTrendPeriod,
    ManagerMetrics,
    ManagerOverview,
    ManagerRanking,
    ManagerSummary,
    NeedsManagerResult,
    OccupancyTrend,
    OccupancyTrendPeriod,
    PropertyDetail,
    PropertyDetailUnit,
    PropertyListItem,
    PropertyOverview,
    PropertySummary,
    RentRollResult,
    RentRollRow,
    RentTrend,
    RentTrendPeriod,
    TenantDetail,
    TenantInRentRoll,
    TrendPeriod,
    UnassignedProperty,
    UnitIssue,
    UnitListItem,
    UnitListResult,
    VacancyTracker,
    VacantUnit,
)
from .dashboard import DashboardResolver
from .leases import LeaseResolver
from .maintenance import MaintenanceResolver
from .managers import ManagerResolver
from .properties import PropertyResolver
from .rent_roll import RentRollResolver
from .scope import property_ids_for_manager, property_ids_for_owner
from .signals import SignalDigest, SignalResolver

__all__ = [
    # Views
    "DashboardResolver",
    "LeaseResolver",
    "MaintenanceResolver",
    "ManagerResolver",
    "PropertyResolver",
    "RentRollResolver",
    "SignalDigest",
    "SignalResolver",
    # Scope helpers
    "property_ids_for_manager",
    "property_ids_for_owner",
    # Read-models
    "AutoAssignResult",
    "DashboardOverview",
    "DelinquencyBoard",
    "DelinquencyTrend",
    "DelinquentTenant",
    "ExpiringLease",
    "LeaseCalendar",
    "LeaseInfo",
    "LeaseInRentRoll",
    "LeaseListItem",
    "LeaseListResult",
    "MaintenanceInRentRoll",
    "MaintenanceItem",
    "MaintenanceListResult",
    "MaintenanceSummaryResult",
    "MaintenanceTrend",
    "MaintenanceTrendPeriod",
    "ManagerMetrics",
    "ManagerOverview",
    "ManagerRanking",
    "ManagerSummary",
    "NeedsManagerResult",
    "OccupancyTrend",
    "OccupancyTrendPeriod",
    "PropertyDetail",
    "PropertyDetailUnit",
    "PropertyListItem",
    "PropertyOverview",
    "PropertySummary",
    "RentRollResult",
    "RentRollRow",
    "RentTrend",
    "RentTrendPeriod",
    "TenantDetail",
    "TenantInRentRoll",
    "TrendPeriod",
    "UnassignedProperty",
    "UnitIssue",
    "UnitListItem",
    "UnitListResult",
    "VacancyTracker",
    "VacantUnit",
]
