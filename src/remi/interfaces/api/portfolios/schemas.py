"""Response schemas for portfolios."""

from __future__ import annotations

from pydantic import BaseModel


class PortfolioListItem(BaseModel):
    id: str
    name: str
    manager: str
    property_count: int
    description: str


class PortfolioListResponse(BaseModel):
    portfolios: list[PortfolioListItem]


class PortfolioDetail(BaseModel):
    id: str
    manager_id: str
    name: str
    description: str
    property_ids: list[str]
    created_at: str


class PropertyInPortfolio(BaseModel):
    id: str
    name: str
    type: str
    units: int
    occupied: int
    monthly_revenue: float


class PortfolioSummary(BaseModel):
    portfolio_id: str
    name: str
    manager: str
    total_properties: int
    total_units: int
    occupied_units: int
    occupancy_rate: float
    monthly_revenue: float
    properties: list[PropertyInPortfolio]
