"""PortfolioQueryService — portfolio listing and summary aggregation.

Pure PropertyStore read-model.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel

from remi.domain.properties.enums import UnitStatus

if TYPE_CHECKING:
    from remi.domain.properties.ports import PropertyStore

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PortfolioListItem(BaseModel):
    id: str
    name: str
    manager: str
    property_count: int
    description: str


class PropertyInPortfolio(BaseModel):
    id: str
    name: str
    type: str
    units: int
    occupied: int
    monthly_revenue: float


class PortfolioSummaryResult(BaseModel):
    portfolio_id: str
    name: str
    manager: str
    total_properties: int
    total_units: int
    occupied_units: int
    occupancy_rate: float
    monthly_revenue: float
    properties: list[PropertyInPortfolio]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PortfolioQueryService:
    """Portfolio listing and summary read models."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_portfolios(
        self, manager_id: str | None = None
    ) -> list[PortfolioListItem]:
        portfolios = await self._ps.list_portfolios(manager_id=manager_id)
        items: list[PortfolioListItem] = []
        for p in portfolios:
            manager = await self._ps.get_manager(p.manager_id)
            props = await self._ps.list_properties(portfolio_id=p.id)
            items.append(PortfolioListItem(
                id=p.id,
                name=p.name,
                manager=manager.name if manager else "Unknown",
                property_count=len(props),
                description=p.description,
            ))
        return items

    async def portfolio_summary(self, portfolio_id: str) -> PortfolioSummaryResult | None:
        portfolio = await self._ps.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        manager = await self._ps.get_manager(portfolio.manager_id)
        properties = await self._ps.list_properties(portfolio_id=portfolio_id)

        total_units = 0
        occupied = 0
        total_revenue = Decimal("0")
        prop_details: list[PropertyInPortfolio] = []

        for prop in properties:
            units = await self._ps.list_units(property_id=prop.id)
            occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
            rev = sum((u.current_rent for u in units), Decimal("0"))
            total_units += len(units)
            occupied += occ
            total_revenue += rev
            prop_details.append(PropertyInPortfolio(
                id=prop.id,
                name=prop.name,
                type=prop.property_type.value,
                units=len(units),
                occupied=occ,
                monthly_revenue=float(rev),
            ))

        return PortfolioSummaryResult(
            portfolio_id=portfolio_id,
            name=portfolio.name,
            manager=manager.name if manager else "Unknown",
            total_properties=len(properties),
            total_units=total_units,
            occupied_units=occupied,
            occupancy_rate=round(occupied / total_units, 3) if total_units else 0,
            monthly_revenue=float(total_revenue),
            properties=prop_details,
        )
