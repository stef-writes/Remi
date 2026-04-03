"""Assets — the physical book.

Address, Property, Unit.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from remi.domain.portfolio.models._helpers import _utcnow
from remi.domain.portfolio.models.enums import (
    OccupancyStatus,
    PropertyType,
    UnitStatus,
    UnitType,
)


class Address(BaseModel, frozen=True):
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"

    def one_line(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


class Property(BaseModel, frozen=True):
    id: str
    portfolio_id: str
    name: str
    address: Address
    property_type: PropertyType = PropertyType.RESIDENTIAL
    year_built: int | None = None
    owner_id: str | None = None
    unit_count: int | None = None
    neighborhood: str | None = None
    year_renovated: int | None = None
    acquisition_date: date | None = None
    management_start_date: date | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Unit(BaseModel, frozen=True):
    id: str
    property_id: str
    unit_number: str
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    unit_type: UnitType | None = None
    market_rent: Decimal = Decimal("0")
    current_rent: Decimal = Decimal("0")
    status: UnitStatus = UnitStatus.VACANT
    occupancy_status: OccupancyStatus | None = None
    days_vacant: int | None = None
    listed_on_website: bool = False
    listed_on_internet: bool = False
    floor: int | None = None
    move_in_date: date | None = None
    move_out_date: date | None = None
    last_turn_cost: Decimal | None = None
    last_turn_days: int | None = None
    source_document_id: str | None = None
