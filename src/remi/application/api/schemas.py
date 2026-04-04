"""HTTP boundary types for all portfolio entity routes.

Read-model types are owned by ``portfolio.queries`` and re-exported here.
Only request types, detail views, and envelope wrappers are defined here.
"""

from __future__ import annotations

from pydantic import BaseModel

from remi.application.services.queries import (
    ExpiringLeaseItem,
    ExpiringLeasesResult,
    MaintenanceItem,
    MaintenanceListResult,
    MaintenanceSummaryResult,
    ManagerRanking,
    ManagerSummary,
    PortfolioListItem,
    PortfolioSummaryResult,
    PropertyDetail,
    PropertyDetailUnit,
    PropertyListItem,
    PropertySummary,
    RentRollResult,
    RentRollRow,
    UnitIssue,
)
from remi.application.core.models.enums import AssetClass

__all__ = [
    "AssetClass",
    "AssignPropertiesRequest",
    "AssignPropertiesResponse",
    "CreateManagerRequest",
    "CreateManagerResponse",
    "CreatePortfolioRequest",
    "CreatePortfolioResponse",
    "ExpiringLeaseItem",
    "ExpiringLeasesResponse",
    "ExpiringLeasesResult",
    "LeaseListItem",
    "LeaseListResponse",
    "MaintenanceItem",
    "MaintenanceListResult",
    "MaintenanceSummaryResult",
    "ManagerListItem",
    "ManagerListResponse",
    "ManagerRanking",
    "ManagerRankingsResponse",
    "ManagerReviewResponse",
    "ManagerSummary",
    "MergeManagersRequest",
    "MergeManagersResponse",
    "PortfolioDetail",
    "PortfolioListItem",
    "PortfolioListResponse",
    "PortfolioSummaryResult",
    "PropertyDetail",
    "PropertyDetailUnit",
    "PropertyListItem",
    "PropertyListResponse",
    "PropertySummary",
    "RentRollResult",
    "RentRollRow",
    "UnitIssue",
    "UnitItem",
    "UnitListResponse",
    "UpdateManagerRequest",
    "UpdatePortfolioRequest",
    "UpdatePropertyRequest",
]


# -- Manager schemas --------------------------------------------------------


class ManagerListItem(BaseModel):
    id: str
    name: str
    email: str
    company: str | None
    portfolio_count: int
    property_count: int
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
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


class ManagerListResponse(BaseModel):
    managers: list[ManagerListItem]


class ManagerRankingsResponse(BaseModel):
    rankings: list[ManagerRanking]
    total: int
    sort_by: str


class CreateManagerRequest(BaseModel):
    name: str
    email: str = ""
    company: str | None = None
    phone: str | None = None


class CreateManagerResponse(BaseModel):
    manager_id: str
    portfolio_id: str
    name: str


class UpdateManagerRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    company: str | None = None
    phone: str | None = None


class MergeManagersRequest(BaseModel):
    source_manager_id: str
    target_manager_id: str


class MergeManagersResponse(BaseModel):
    target_manager_id: str
    properties_moved: int
    source_deleted: bool


class AssignPropertiesRequest(BaseModel):
    property_ids: list[str]


class AssignPropertiesResponse(BaseModel):
    manager_id: str
    assigned: int
    already_assigned: int
    not_found: list[str]


class ManagerReviewResponse(BaseModel):
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


# -- Portfolio schemas -------------------------------------------------------


class PortfolioListResponse(BaseModel):
    portfolios: list[PortfolioListItem]


class PortfolioDetail(BaseModel):
    id: str
    manager_id: str
    name: str
    description: str
    asset_class: AssetClass | None
    strategy: str | None
    target_occupancy: float | None
    market: str | None
    property_ids: list[str]
    created_at: str


class CreatePortfolioRequest(BaseModel):
    manager_id: str
    name: str
    description: str = ""
    asset_class: AssetClass | None = None
    strategy: str | None = None
    target_occupancy: float | None = None
    market: str | None = None


class CreatePortfolioResponse(BaseModel):
    portfolio_id: str
    manager_id: str
    name: str


class UpdatePortfolioRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    asset_class: AssetClass | None = None
    strategy: str | None = None
    target_occupancy: float | None = None
    market: str | None = None


# -- Property schemas -------------------------------------------------------


class PropertyListResponse(BaseModel):
    properties: list[PropertyListItem]


class UnitListResponse(BaseModel):
    property_id: str
    count: int
    units: list[PropertyDetailUnit]


class UpdatePropertyRequest(BaseModel):
    name: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    portfolio_id: str | None = None


# -- Lease schemas -----------------------------------------------------------


class LeaseListItem(BaseModel):
    id: str
    tenant: str
    unit_id: str
    property_id: str
    start: str
    end: str
    rent: float
    status: str


class LeaseListResponse(BaseModel):
    count: int
    leases: list[LeaseListItem]


class ExpiringLeasesResponse(BaseModel):
    days_window: int
    count: int
    leases: list[ExpiringLeaseItem]


# -- Unit schemas ------------------------------------------------------------


class UnitItem(BaseModel, frozen=True):
    id: str
    unit_number: str
    property: str
    property_id: str
    status: str
    bedrooms: int | None = None
    sqft: int | None = None
    market_rent: float
    current_rent: float


class UnitCrossPropertyResponse(BaseModel, frozen=True):
    count: int
    units: list[UnitItem]
