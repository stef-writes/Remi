"""Shared read-model types for portfolio query services."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from remi.application.core.models import Address


# -- Portfolio entities ------------------------------------------------------


class PortfolioListItem(BaseModel):
    id: str
    name: str
    manager: str
    property_count: int
    description: str


class PropertyInPortfolio(BaseModel):
    id: str
    name: str
    type: str
    units: int
    occupied: int
    monthly_revenue: float


class PortfolioSummaryResult(BaseModel):
    portfolio_id: str
    name: str
    manager: str
    total_properties: int
    total_units: int
    occupied_units: int
    occupancy_rate: float
    monthly_revenue: float
    properties: list[PropertyInPortfolio]


class PropertyListItem(BaseModel):
    id: str
    name: str
    address: str
    type: str
    year_built: int | None
    total_units: int
    occupied: int


class PropertyDetailUnit(BaseModel):
    id: str
    property_id: str
    unit_number: str
    status: str
    occupancy_status: str | None = None
    bedrooms: int | None
    bathrooms: float | None
    sqft: int | None
    floor: int | None
    market_rent: float
    current_rent: float


class PropertyDetail(BaseModel):
    id: str
    name: str
    address: Address
    property_type: str
    year_built: int | None
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    monthly_revenue: float
    active_leases: int
    units: list[PropertyDetailUnit]


class ExpiringLeaseItem(BaseModel):
    lease_id: str
    tenant: str
    unit: str
    property: str
    monthly_rent: float
    end_date: str
    days_left: int


class ExpiringLeasesResult(BaseModel):
    days_window: int
    count: int
    leases: list[ExpiringLeaseItem]


class MaintenanceItem(BaseModel):
    id: str
    property_id: str
    unit_id: str
    title: str
    category: str
    priority: str
    status: str
    cost: float | None
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
    portfolio_id: str
    portfolio_name: str
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


class ManagerSummary(BaseModel):
    manager_id: str
    name: str
    email: str
    company: str | None
    portfolio_count: int
    property_count: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_market_rent: float
    total_actual_rent: float
    total_loss_to_lease: float
    total_vacancy_loss: float
    open_maintenance: int
    emergency_maintenance: int
    expiring_leases_90d: int
    expired_leases: int
    below_market_units: int
    delinquent_count: int
    total_delinquent_balance: float
    properties: list[PropertySummary]
    top_issues: list[UnitIssue]


class ManagerRanking(BaseModel, frozen=True):
    manager_id: str
    name: str
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_actual_rent: float
    total_market_rent: float
    total_loss_to_lease: float
    total_vacancy_loss: float
    delinquent_count: int
    total_delinquent_balance: float
    delinquency_rate: float
    open_maintenance: int
    expiring_leases_90d: int
    property_count: int


# -- Dashboard models --------------------------------------------------------


class ManagerOverview(BaseModel):
    manager_id: str
    manager_name: str
    portfolio_count: int
    property_count: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_monthly_rent: float
    total_market_rent: float
    loss_to_lease: float


class PortfolioOverview(BaseModel):
    total_managers: int
    total_portfolios: int
    total_properties: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    total_monthly_rent: float
    total_market_rent: float
    total_loss_to_lease: float
    managers: list[ManagerOverview]


class DelinquentTenant(BaseModel):
    tenant_id: str
    tenant_name: str
    status: str
    property_name: str
    unit_number: str
    balance_owed: float
    balance_0_30: float
    balance_30_plus: float
    last_payment_date: str | None
    tags: list[str]
    delinquency_notes: str | None = None


class DelinquencyBoard(BaseModel):
    total_delinquent: int
    total_balance: float
    tenants: list[DelinquentTenant]


class ExpiringLease(BaseModel):
    lease_id: str
    tenant_name: str
    property_name: str
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


class RentRollUnit(BaseModel):
    unit_id: str
    unit_number: str
    occupancy_status: str | None
    bedrooms: int | None
    bathrooms: float | None
    sqft: int | None
    current_rent: float
    market_rent: float
    rent_gap: float
    tenant_name: str | None
    lease_end: str | None
    days_to_expiry: int | None


class RentRollView(BaseModel):
    property_id: str
    property_name: str
    total_units: int
    occupied: int
    vacant: int
    total_monthly_rent: float
    total_market_rent: float
    loss_to_lease: float
    units: list[RentRollUnit]


class VacantUnit(BaseModel):
    unit_id: str
    unit_number: str
    property_id: str
    property_name: str
    occupancy_status: str | None
    days_vacant: int | None
    market_rent: float
    listed_on_website: bool
    listed_on_internet: bool


class VacancyTracker(BaseModel):
    total_vacant: int
    total_notice: int
    total_market_rent_at_risk: float
    avg_days_vacant: float | None
    units: list[VacantUnit]


# -- Auto-assign result -----------------------------------------------------


@dataclass
class AutoAssignResult:
    assigned: int
    unresolved: int
    tags_available: int
    message: str
