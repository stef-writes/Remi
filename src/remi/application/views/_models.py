"""Shared read-model types for domain query services."""

from __future__ import annotations

from pydantic import BaseModel

from remi.application.core.models import Address


class PropertyListItem(BaseModel):
    id: str
    name: str
    address: str
    type: str
    year_built: int | None
    total_units: int
    occupied: int
    manager_id: str | None = None
    owner_id: str | None = None
    owner_name: str | None = None


class PropertyDetailUnit(BaseModel):
    id: str
    property_id: str
    unit_number: str
    status: str  # derived: "occupied" | "vacant"
    occupancy_status: str | None = None  # derived from lease
    bedrooms: int | None
    bathrooms: float | None
    sqft: int | None
    floor: int | None
    market_rent: float
    current_rent: float  # derived from active lease


class PropertyDetail(BaseModel):
    id: str
    name: str
    address: Address
    property_type: str
    year_built: int | None
    manager_id: str | None = None
    manager_name: str | None = None
    owner_id: str | None = None
    owner_name: str | None = None
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    monthly_revenue: float
    active_leases: int
    units: list[PropertyDetailUnit]


class MaintenanceItem(BaseModel):
    id: str
    property_id: str
    unit_id: str
    title: str
    description: str
    category: str
    priority: str
    status: str
    source: str | None
    vendor: str | None
    cost: float | None
    scheduled_date: str | None
    completed_date: str | None  # when the work was actually done
    created: str
    resolved: str | None


class MaintenanceListResult(BaseModel):
    count: int
    requests: list[MaintenanceItem]


class MaintenanceSummaryResult(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    total_cost: float


# -- Lease / unit list models -------------------------------------------------


class LeaseListItem(BaseModel):
    id: str
    tenant: str
    unit_id: str
    property_id: str
    start: str
    end: str
    rent: float
    status: str


class LeaseListResult(BaseModel):
    count: int
    leases: list[LeaseListItem]


class UnitListItem(BaseModel):
    id: str
    unit_number: str
    property_name: str
    property_id: str
    status: str
    bedrooms: int | None = None
    sqft: int | None = None
    market_rent: float
    current_rent: float


class UnitListResult(BaseModel):
    count: int
    units: list[UnitListItem]


# -- Rent-roll models --------------------------------------------------------


class LeaseInRentRoll(BaseModel):
    id: str
    status: str
    start_date: str
    end_date: str
    monthly_rent: float
    deposit: float
    days_to_expiry: int | None


class TenantInRentRoll(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None


class MaintenanceInRentRoll(BaseModel):
    id: str
    title: str
    category: str
    priority: str
    status: str
    cost: float | None


class RentRollRow(BaseModel):
    unit_id: str
    unit_number: str
    floor: int | None
    bedrooms: int | None
    bathrooms: float | None
    sqft: int | None
    status: str
    market_rent: float
    current_rent: float
    rent_gap: float
    pct_below_market: float
    lease: LeaseInRentRoll | None
    tenant: TenantInRentRoll | None
    open_maintenance: int
    maintenance_items: list[MaintenanceInRentRoll]
    issues: list[str]


class RentRollResult(BaseModel):
    property_id: str
    property_name: str
    total_units: int
    occupied: int
    vacant: int
    total_market_rent: float
    total_actual_rent: float
    total_loss_to_lease: float
    total_vacancy_loss: float
    rows: list[RentRollRow]


# -- Manager review models ---------------------------------------------------


class PropertySummary(BaseModel):
    property_id: str
    property_name: str
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    monthly_actual: float
    monthly_market: float
    loss_to_lease: float
    vacancy_loss: float
    open_maintenance: int
    emergency_maintenance: int
    expiring_leases: int
    expired_leases: int
    below_market_units: int
    issue_count: int


class UnitIssue(BaseModel):
    property_id: str
    property_name: str
    unit_id: str
    unit_number: str
    issues: list[str]
    monthly_impact: float


class ManagerMetrics(BaseModel, frozen=True):
    """Shared portfolio metrics embedded in every manager view."""

    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_actual_rent: float
    total_market_rent: float
    loss_to_lease: float
    vacancy_loss: float
    open_maintenance: int
    expiring_leases_90d: int


class ManagerSummary(BaseModel):
    """Full review with property breakdown and issues."""

    manager_id: str
    name: str
    email: str
    company: str | None
    property_count: int
    metrics: ManagerMetrics
    delinquent_count: int
    total_delinquent_balance: float
    expired_leases: int
    below_market_units: int
    emergency_maintenance: int
    properties: list[PropertySummary]
    top_issues: list[UnitIssue]


class ManagerRanking(BaseModel, frozen=True):
    """Ranking table row."""

    manager_id: str
    name: str
    property_count: int
    metrics: ManagerMetrics
    delinquent_count: int
    total_delinquent_balance: float
    delinquency_rate: float


# -- Dashboard models --------------------------------------------------------


class ManagerOverview(BaseModel):
    """Dashboard card."""

    manager_id: str
    manager_name: str
    property_count: int
    metrics: ManagerMetrics


class PropertyOverview(BaseModel):
    """Per-property row in the dashboard grid."""

    property_id: str
    property_name: str
    address: str
    manager_id: str | None = None
    manager_name: str | None = None
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    monthly_rent: float
    market_rent: float
    loss_to_lease: float
    open_maintenance: int


class DashboardOverview(BaseModel):
    total_properties: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_monthly_rent: float
    total_market_rent: float
    total_loss_to_lease: float
    properties: list[PropertyOverview]
    total_managers: int = 0
    managers: list[ManagerOverview] = []


class DelinquentTenant(BaseModel):
    tenant_id: str
    tenant_name: str
    status: str
    property_id: str | None = None
    property_name: str
    unit_id: str | None = None
    unit_number: str
    balance_owed: float  # from latest BalanceObservation
    balance_0_30: float  # from latest BalanceObservation
    balance_30_plus: float  # from latest BalanceObservation
    last_payment_date: str | None  # from latest BalanceObservation
    delinquency_notes: str | None = None


class DelinquencyBoard(BaseModel):
    total_delinquent: int
    total_balance: float
    tenants: list[DelinquentTenant]


class ExpiringLease(BaseModel):
    lease_id: str
    tenant_name: str
    property_id: str
    property_name: str
    unit_id: str
    unit_number: str
    monthly_rent: float
    market_rent: float
    end_date: str
    days_left: int
    is_month_to_month: bool


class LeaseCalendar(BaseModel):
    days_window: int
    total_expiring: int
    month_to_month_count: int
    leases: list[ExpiringLease]


class VacantUnit(BaseModel):
    unit_id: str
    unit_number: str
    property_id: str
    property_name: str
    occupancy_status: str | None
    days_vacant: int | None
    market_rent: float


class VacancyTracker(BaseModel):
    total_vacant: int
    total_notice: int
    total_market_rent_at_risk: float
    avg_days_vacant: float | None
    units: list[VacantUnit]


# -- Trend models ------------------------------------------------------------


class TrendPeriod(BaseModel, frozen=True):
    """A single data point in a time-series trend."""

    period: str
    total_balance: float
    tenant_count: int
    avg_balance: float
    max_balance: float


class DelinquencyTrend(BaseModel, frozen=True):
    """Delinquency totals over time, grouped by month."""

    manager_id: str | None
    periods: list[TrendPeriod]
    period_count: int
    direction: str  # "improving" | "worsening" | "stable" | "insufficient_data"


class OccupancyTrendPeriod(BaseModel, frozen=True):
    period: str
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float


class OccupancyTrend(BaseModel, frozen=True):
    manager_id: str | None
    property_id: str | None
    periods: list[OccupancyTrendPeriod]
    period_count: int
    direction: str


class RentTrendPeriod(BaseModel, frozen=True):
    period: str
    avg_rent: float
    median_rent: float
    total_rent: float
    unit_count: int


class RentTrend(BaseModel, frozen=True):
    manager_id: str | None
    property_id: str | None
    periods: list[RentTrendPeriod]
    period_count: int
    direction: str


class MaintenanceTrendPeriod(BaseModel, frozen=True):
    """One month of maintenance activity."""

    period: str
    opened: int
    completed: int
    net_open: int
    total_cost: float
    avg_resolution_days: float | None
    by_category: dict[str, int] = {}


class MaintenanceTrend(BaseModel, frozen=True):
    manager_id: str | None
    property_id: str | None
    unit_id: str | None
    periods: list[MaintenanceTrendPeriod]
    period_count: int
    direction: str  # "improving" | "worsening" | "stable" | "insufficient_data"


# -- Tenant models -----------------------------------------------------------


class LeaseInfo(BaseModel, frozen=True):
    lease_id: str
    unit: str
    property_id: str
    start: str
    end: str
    monthly_rent: float
    status: str


class TenantDetail(BaseModel, frozen=True):
    tenant_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    leases: list[LeaseInfo]


# -- Dashboard models -------------------------------------------------------


class UnassignedProperty(BaseModel, frozen=True):
    id: str
    name: str
    address: str


class NeedsManagerResult(BaseModel, frozen=True):
    total: int
    properties: list[UnassignedProperty]


# -- Auto-assign result -----------------------------------------------------


class AutoAssignResult(BaseModel, frozen=True):
    assigned: int
    unresolved: int
    tags_available: int
    message: str
