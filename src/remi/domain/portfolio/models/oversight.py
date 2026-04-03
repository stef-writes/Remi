"""Oversight — who's responsible.

Owner, PropertyManager, Portfolio.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from remi.domain.portfolio.models.enums import AssetClass
from remi.domain.portfolio.models._helpers import _utcnow


class Owner(BaseModel, frozen=True):
    """The legal entity that owns a property asset.

    May be the management company itself (through its development arm),
    an individual investor, an LP, or a trust.  Owners are active
    participants in operational decisions — approving payment plans,
    authorizing non-renewals, funding capital improvements.
    """

    id: str
    name: str
    entity_type_label: str = ""
    email: str = ""
    phone: str | None = None
    property_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class PropertyManager(BaseModel, frozen=True):
    id: str
    name: str
    email: str = ""
    company: str | None = None
    phone: str | None = None
    manager_tag: str | None = None
    title: str | None = None
    territory: str | None = None
    max_units: int | None = None
    license_number: str | None = None
    portfolio_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Portfolio(BaseModel, frozen=True):
    id: str
    manager_id: str
    name: str
    description: str = ""
    asset_class: AssetClass | None = None
    strategy: str | None = None
    target_occupancy: float | None = None
    market: str | None = None
    property_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
