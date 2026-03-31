"""REST endpoints for cross-property unit queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from remi.api.dependencies import get_container
from remi.models.properties import UnitStatus

if TYPE_CHECKING:
    from remi.config.container import Container

router = APIRouter(prefix="/units", tags=["units"])


class UnitItem(BaseModel, frozen=True):
    id: str
    unit_number: str
    property: str
    property_id: str
    status: str
    bedrooms: int | None = None
    sqft: int | None = None
    market_rent: float
    current_rent: float


class UnitListResponse(BaseModel, frozen=True):
    count: int
    units: list[UnitItem]


@router.get("", response_model=UnitListResponse)
async def list_all_units(
    property_id: str | None = None,
    status: str | None = None,
    container: Container = Depends(get_container),
) -> UnitListResponse:
    unit_status = UnitStatus(status) if status else None
    units = await container.property_store.list_units(
        property_id=property_id,
        status=unit_status,
    )
    items: list[UnitItem] = []
    for u in units:
        prop = await container.property_store.get_property(u.property_id)
        items.append(
            UnitItem(
                id=u.id,
                unit_number=u.unit_number,
                property=prop.name if prop else u.property_id,
                property_id=u.property_id,
                status=u.status.value,
                bedrooms=u.bedrooms,
                sqft=u.sqft,
                market_rent=float(u.market_rent),
                current_rent=float(u.current_rent),
            )
        )
    return UnitListResponse(count=len(items), units=items)
