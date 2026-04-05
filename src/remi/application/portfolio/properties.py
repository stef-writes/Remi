"""Properties — list, detail, and computed fields."""

from __future__ import annotations

from decimal import Decimal

from remi.application.core.models import LeaseStatus, UnitStatus
from remi.application.core.protocols import PropertyStore

from ._models import (
    PropertyDetail,
    PropertyDetailUnit,
    PropertyListItem,
)


class PropertyResolver:
    """Entity resolver for properties."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_properties(self, portfolio_id: str | None = None) -> list[PropertyListItem]:
        properties = await self._ps.list_properties(portfolio_id=portfolio_id)
        items: list[PropertyListItem] = []
        for p in properties:
            units = await self._ps.list_units(property_id=p.id)
            occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
            items.append(
                PropertyListItem(
                    id=p.id,
                    name=p.name,
                    address=p.address.one_line(),
                    type=p.property_type.value,
                    year_built=p.year_built,
                    total_units=len(units),
                    occupied=occ,
                )
            )
        return items

    async def get_property_detail(self, property_id: str) -> PropertyDetail | None:
        prop = await self._ps.get_property(property_id)
        if not prop:
            return None

        units = await self._ps.list_units(property_id=property_id)
        active_leases = await self._ps.list_leases(
            property_id=property_id, status=LeaseStatus.ACTIVE
        )
        occupied = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
        vacant = sum(1 for u in units if u.status == UnitStatus.VACANT)
        revenue = sum((u.current_rent for u in units), Decimal("0"))

        portfolio_id: str | None = None
        portfolio_name: str | None = None
        manager_id: str | None = None
        manager_name: str | None = None
        if prop.portfolio_id:
            portfolio = await self._ps.get_portfolio(prop.portfolio_id)
            if portfolio:
                portfolio_id = portfolio.id
                portfolio_name = portfolio.name
                if portfolio.manager_id:
                    manager = await self._ps.get_manager(portfolio.manager_id)
                    if manager:
                        manager_id = manager.id
                        manager_name = manager.name

        return PropertyDetail(
            id=property_id,
            name=prop.name,
            address=prop.address,
            property_type=prop.property_type.value,
            year_built=prop.year_built,
            portfolio_id=portfolio_id,
            portfolio_name=portfolio_name,
            manager_id=manager_id,
            manager_name=manager_name,
            total_units=len(units),
            occupied=occupied,
            vacant=vacant,
            occupancy_rate=round(occupied / len(units), 3) if units else 0,
            monthly_revenue=float(revenue),
            active_leases=len(active_leases),
            units=[
                PropertyDetailUnit(
                    id=u.id,
                    property_id=property_id,
                    unit_number=u.unit_number,
                    status=u.status.value,
                    occupancy_status=u.occupancy_status.value if u.occupancy_status else None,
                    bedrooms=u.bedrooms,
                    bathrooms=u.bathrooms,
                    sqft=u.sqft,
                    floor=u.floor,
                    market_rent=float(u.market_rent),
                    current_rent=float(u.current_rent),
                )
                for u in units
            ],
        )
