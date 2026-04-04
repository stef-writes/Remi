"""REST endpoints for cross-property unit queries."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from remi.application.api.schemas import UnitCrossPropertyResponse, UnitItem
from remi.application.core.models import UnitStatus
from remi.application.core.protocols import PropertyStore
from remi.application.api.dependencies import get_property_store

router = APIRouter(prefix="/units", tags=["units"])


@router.get("", response_model=UnitCrossPropertyResponse)
async def list_all_units(
    property_id: str | None = None,
    status: str | None = None,
    ps: PropertyStore = Depends(get_property_store),
) -> UnitCrossPropertyResponse:
    unit_status = UnitStatus(status) if status else None
    units = await ps.list_units(property_id=property_id, status=unit_status)
    items: list[UnitItem] = []
    for u in units:
        prop = await ps.get_property(u.property_id)
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
    return UnitCrossPropertyResponse(count=len(items), units=items)
