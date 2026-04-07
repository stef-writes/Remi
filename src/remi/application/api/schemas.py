"""HTTP boundary types — request bodies and envelope wrappers.

Read-model types are owned by ``application.views``. Only the types used
as field types in envelope classes here are imported; routes import
read-models directly from ``views`` when needed as response_model.
"""

from __future__ import annotations

from pydantic import BaseModel

from remi.application.views import (
    ManagerRanking,
    ManagerSummary,
    PropertyDetail,
    PropertyDetailUnit,
    PropertyListItem,
)

__all__ = [
    "AssignPropertiesRequest",
    "AssignPropertiesResponse",
    "CreateLeaseRequest",
    "CreateLeaseResponse",
    "CreateMaintenanceRequest",
    "CreateMaintenanceResponse",
    "CreateManagerRequest",
    "CreateManagerResponse",
    "CreatePropertyRequest",
    "CreatePropertyResponse",
    "CreateTenantRequest",
    "CreateTenantResponse",
    "CreateUnitRequest",
    "CreateUnitResponse",
    "ManagerListResponse",
    "ManagerRankingsResponse",
    "MergeManagersRequest",
    "MergeManagersResponse",
    "PropertyDetail",
    "PropertyDetailUnit",
    "PropertyListItem",
    "PropertyListResponse",
    "UnitListResponse",
    "UpdateLeaseRequest",
    "UpdateMaintenanceRequest",
    "UpdateManagerRequest",
    "UpdatePropertyRequest",
    "UpdateTenantRequest",
    "UpdateUnitRequest",
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


# -- Property schemas -------------------------------------------------------


class PropertyListResponse(BaseModel):
    properties: list[PropertyListItem]


class UnitListResponse(BaseModel):
    property_id: str
    count: int
    units: list[PropertyDetailUnit]


class CreatePropertyRequest(BaseModel):
    name: str
    manager_id: str | None = None
    owner_id: str | None = None
    street: str
    city: str
    state: str
    zip_code: str
    property_type: str = "multi_family"
    year_built: int | None = None


class CreatePropertyResponse(BaseModel):
    property_id: str
    name: str


class UpdatePropertyRequest(BaseModel):
    name: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    manager_id: str | None = None
    owner_id: str | None = None


# -- Unit schemas -----------------------------------------------------------


class CreateUnitRequest(BaseModel):
    property_id: str
    unit_number: str
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    market_rent: float = 0
    floor: int | None = None


class CreateUnitResponse(BaseModel):
    unit_id: str
    property_id: str
    unit_number: str


class UpdateUnitRequest(BaseModel):
    unit_number: str | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    market_rent: float | None = None
    floor: int | None = None


# -- Lease schemas ----------------------------------------------------------


class CreateLeaseRequest(BaseModel):
    unit_id: str
    tenant_id: str
    property_id: str
    start_date: str
    end_date: str
    monthly_rent: float
    deposit: float = 0
    status: str = "active"


class CreateLeaseResponse(BaseModel):
    lease_id: str
    unit_id: str
    tenant_id: str
    property_id: str


class UpdateLeaseRequest(BaseModel):
    monthly_rent: float | None = None
    status: str | None = None
    end_date: str | None = None
    renewal_status: str | None = None
    is_month_to_month: bool | None = None


# -- Tenant schemas ---------------------------------------------------------


class CreateTenantRequest(BaseModel):
    name: str
    property_id: str
    email: str = ""
    phone: str | None = None


class CreateTenantResponse(BaseModel):
    tenant_id: str
    name: str


class UpdateTenantRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None  # TenantStatus — eviction tracking only


# -- Maintenance schemas ----------------------------------------------------


class CreateMaintenanceRequest(BaseModel):
    unit_id: str
    property_id: str
    title: str
    description: str = ""
    category: str = "general"
    priority: str = "medium"


class CreateMaintenanceResponse(BaseModel):
    request_id: str
    title: str
    property_id: str
    unit_id: str


class UpdateMaintenanceRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    vendor: str | None = None
    cost: float | None = None
