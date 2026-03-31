"""Response schemas for properties."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PropertyListItem(BaseModel):
    id: str
    name: str
    address: str
    type: str
    year_built: int | None
    total_units: int
    occupied: int


class PropertyListResponse(BaseModel):
    properties: list[PropertyListItem]


class UnitSummary(BaseModel):
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
    address: dict[str, Any]
    property_type: str
    year_built: int | None
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    monthly_revenue: float
    active_leases: int
    units: list[UnitSummary]


class UnitListResponse(BaseModel):
    property_id: str
    count: int
    units: list[dict[str, Any]]


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


class RentRollResponse(BaseModel):
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
