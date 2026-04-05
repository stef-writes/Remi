"""HTTP boundary types for all portfolio entity routes.

Read-model types are owned by ``application.portfolio`` and re-exported here
where routers need them. Only request types and envelope wrappers are
defined in this file.
"""

from __future__ import annotations

from pydantic import BaseModel

from remi.application.core.models.enums import AssetClass
from remi.application.portfolio import (
    ExpiringLeaseItem,
    ExpiringLeasesResult,
    LeaseListItem,
    LeaseListResult,
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
    UnitListItem,
    UnitListResult,
)

__all__ = [
    "AssetClass",
    "AssignPropertiesRequest",
    "AssignPropertiesResponse",
    "CreateManagerRequest",
    "CreateManagerResponse",
    "CreatePortfolioRequest",
    "CreatePortfolioResponse",
    "ExpiringLeaseItem",
    "ExpiringLeasesResult",
    "LeaseListItem",
    "LeaseListResult",
    "MaintenanceItem",
    "MaintenanceListResult",
    "MaintenanceSummaryResult",
    "ManagerListResponse",
    "ManagerRanking",
    "ManagerRankingsResponse",
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
    "UnitListItem",
    "UnitListResponse",
    "UnitListResult",
    "UpdateManagerRequest",
    "UpdatePortfolioRequest",
    "UpdatePropertyRequest",
]


# -- Manager schemas --------------------------------------------------------


class ManagerListResponse(BaseModel):
    managers: list[ManagerSummary]


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
