"""PropertyQueryService — property listing and detail aggregation.

Pure PropertyStore read-model: no LLM, no document store.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from remi.domain.properties.enums import LeaseStatus, UnitStatus
from remi.domain.properties.ports import PropertyStore


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PropertyListItem(BaseModel):
    id: str
    name: str
    address: str
    type: str
    year_built: int | None
    total_units: int
    occupied: int


class PropertyDetailUnit(BaseModel):
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
    address: dict
    property_type: str
    year_built: int | None
    total_units: int
    occupied: int
    vacant: int
    occupancy_rate: float
    monthly_revenue: float
    active_leases: int
    units: list[PropertyDetailUnit]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PropertyQueryService:
    """Property listing and detail read models."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_properties(
        self, portfolio_id: str | None = None
    ) -> list[PropertyListItem]:
        properties = await self._ps.list_properties(portfolio_id=portfolio_id)
        items: list[PropertyListItem] = []
        for p in properties:
            units = await self._ps.list_units(property_id=p.id)
            occ = sum(1 for u in units if u.status == UnitStatus.OCCUPIED)
            items.append(PropertyListItem(
                id=p.id,
                name=p.name,
                address=p.address.one_line(),
                type=p.property_type.value,
                year_built=p.year_built,
                total_units=len(units),
                occupied=occ,
            ))
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

        return PropertyDetail(
            id=property_id,
            name=prop.name,
            address=prop.address.model_dump(),
            property_type=prop.property_type.value,
            year_built=prop.year_built,
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
