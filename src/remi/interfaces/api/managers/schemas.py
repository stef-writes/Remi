"""Response schemas for property managers."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class ManagerListResponse(BaseModel):
    managers: list[ManagerListItem]


class CreateManagerRequest(BaseModel):
    name: str
    email: str = ""
    company: str | None = None
    phone: str | None = None


class CreateManagerResponse(BaseModel):
    manager_id: str
    portfolio_id: str
    name: str


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
    properties: list[PropertySummary]
    top_issues: list[UnitIssue]
