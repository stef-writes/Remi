"""SQLModel table definitions mirroring models.properties.

These are mutable DB-row objects — the store layer converts to/from the
frozen Pydantic read models that the rest of the app uses.

Naming convention: ``<Entity>Row`` to distinguish from the Pydantic DTOs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PropertyManagerRow(SQLModel, table=True):
    __tablename__ = "property_managers"

    id: str = Field(primary_key=True)
    name: str
    email: str = ""
    company: str | None = None
    phone: str | None = None
    manager_tag: str | None = None
    portfolio_ids: list[str] = Field(default_factory=list, sa_type=sa.JSON)
    created_at: datetime = Field(default_factory=_utcnow)


class PortfolioRow(SQLModel, table=True):
    __tablename__ = "portfolios"

    id: str = Field(primary_key=True)
    manager_id: str = Field(index=True)
    name: str
    description: str = ""
    property_ids: list[str] = Field(default_factory=list, sa_type=sa.JSON)
    created_at: datetime = Field(default_factory=_utcnow)


class PropertyRow(SQLModel, table=True):
    __tablename__ = "properties"

    id: str = Field(primary_key=True)
    portfolio_id: str = Field(index=True)
    name: str
    property_type: str = "residential"
    year_built: int | None = None
    # Address stored as individual columns for queryability.
    address_street: str = ""
    address_city: str = ""
    address_state: str = ""
    address_zip_code: str = ""
    address_country: str = "US"
    created_at: datetime = Field(default_factory=_utcnow)


class UnitRow(SQLModel, table=True):
    __tablename__ = "units"

    id: str = Field(primary_key=True)
    property_id: str = Field(index=True)
    unit_number: str
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    market_rent: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    current_rent: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    status: str = "vacant"
    occupancy_status: str | None = None
    days_vacant: int | None = None
    listed_on_website: bool = False
    listed_on_internet: bool = False
    floor: int | None = None


class LeaseRow(SQLModel, table=True):
    __tablename__ = "leases"

    id: str = Field(primary_key=True)
    unit_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    property_id: str = Field(index=True)
    start_date: date
    end_date: date
    monthly_rent: Decimal = Field(sa_type=sa.Numeric(12, 2))
    deposit: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    status: str = "active"
    market_rent: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    is_month_to_month: bool = False


class TenantRow(SQLModel, table=True):
    __tablename__ = "tenants"

    id: str = Field(primary_key=True)
    name: str
    email: str = ""
    phone: str | None = None
    status: str = "current"
    balance_owed: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    balance_0_30: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    balance_30_plus: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    last_payment_date: date | None = None
    tags: list[str] = Field(default_factory=list, sa_type=sa.JSON)
    lease_ids: list[str] = Field(default_factory=list, sa_type=sa.JSON)
    created_at: datetime = Field(default_factory=_utcnow)


class MaintenanceRequestRow(SQLModel, table=True):
    __tablename__ = "maintenance_requests"

    id: str = Field(primary_key=True)
    unit_id: str = Field(index=True)
    property_id: str = Field(index=True)
    tenant_id: str | None = None
    category: str = "general"
    priority: str = "medium"
    title: str = ""
    description: str = ""
    status: str = "open"
    created_at: datetime = Field(default_factory=_utcnow)
    resolved_at: datetime | None = None
    cost: Decimal | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    vendor: str | None = None
