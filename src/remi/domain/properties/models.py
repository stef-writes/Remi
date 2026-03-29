"""Core real estate domain entities."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)

from remi.domain.properties.enums import (
    LeaseStatus,
    MaintenanceCategory,
    MaintenanceStatus,
    OccupancyStatus,
    Priority,
    PropertyType,
    TenantStatus,
    UnitStatus,
)


class Address(BaseModel, frozen=True):
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"

    def one_line(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


class PropertyManager(BaseModel, frozen=True):
    id: str
    name: str
    email: str = ""
    company: str | None = None
    phone: str | None = None
    manager_tag: str | None = None
    portfolio_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Portfolio(BaseModel, frozen=True):
    id: str
    manager_id: str
    name: str
    description: str = ""
    property_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Property(BaseModel, frozen=True):
    id: str
    portfolio_id: str
    name: str
    address: Address
    property_type: PropertyType = PropertyType.RESIDENTIAL
    year_built: int | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Unit(BaseModel, frozen=True):
    id: str
    property_id: str
    unit_number: str
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    market_rent: Decimal = Decimal("0")
    current_rent: Decimal = Decimal("0")
    status: UnitStatus = UnitStatus.VACANT
    occupancy_status: OccupancyStatus | None = None
    days_vacant: int | None = None
    listed_on_website: bool = False
    listed_on_internet: bool = False
    floor: int | None = None


class Lease(BaseModel, frozen=True):
    id: str
    unit_id: str
    tenant_id: str
    property_id: str
    start_date: date
    end_date: date
    monthly_rent: Decimal
    deposit: Decimal = Decimal("0")
    status: LeaseStatus = LeaseStatus.ACTIVE
    market_rent: Decimal = Decimal("0")
    is_month_to_month: bool = False


class Tenant(BaseModel, frozen=True):
    id: str
    name: str
    email: str = ""
    phone: str | None = None
    status: TenantStatus = TenantStatus.CURRENT
    balance_owed: Decimal = Decimal("0")
    balance_0_30: Decimal = Decimal("0")
    balance_30_plus: Decimal = Decimal("0")
    last_payment_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    lease_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class MaintenanceRequest(BaseModel, frozen=True):
    id: str
    unit_id: str
    property_id: str
    tenant_id: str | None = None
    category: MaintenanceCategory = MaintenanceCategory.GENERAL
    priority: Priority = Priority.MEDIUM
    title: str = ""
    description: str = ""
    status: MaintenanceStatus = MaintenanceStatus.OPEN
    created_at: datetime = Field(default_factory=_utcnow)
    resolved_at: datetime | None = None
    cost: Decimal | None = None
    vendor: str | None = None
