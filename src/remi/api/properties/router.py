"""REST endpoints for properties and units."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from remi.api.dependencies import get_property_query, get_property_store, get_rent_roll_service
from remi.api.properties.schemas import (
    PropertyDetail,
    PropertyListItem,
    PropertyListResponse,
    RentRollResponse,
    UnitListResponse,
    UnitSummary,
)
from remi.models.properties import Address, PropertyStore, UnitStatus
from remi.services.property_queries import PropertyQueryService
from remi.services.rent_roll import RentRollService

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=PropertyListResponse)
async def list_properties(
    portfolio_id: str | None = None,
    svc: PropertyQueryService = Depends(get_property_query),
) -> PropertyListResponse:
    items = await svc.list_properties(portfolio_id=portfolio_id)
    return PropertyListResponse(
        properties=[PropertyListItem(**item.model_dump()) for item in items]
    )


@router.get("/{property_id}", response_model=PropertyDetail)
async def get_property(
    property_id: str,
    svc: PropertyQueryService = Depends(get_property_query),
) -> PropertyDetail:
    detail = await svc.get_property_detail(property_id)
    if not detail:
        raise HTTPException(404, f"Property '{property_id}' not found")
    return PropertyDetail(
        id=detail.id,
        name=detail.name,
        address=detail.address,
        property_type=detail.property_type,
        year_built=detail.year_built,
        total_units=detail.total_units,
        occupied=detail.occupied,
        vacant=detail.vacant,
        occupancy_rate=detail.occupancy_rate,
        monthly_revenue=detail.monthly_revenue,
        active_leases=detail.active_leases,
        units=[UnitSummary(**u.model_dump()) for u in detail.units],
    )


@router.get("/{property_id}/units", response_model=UnitListResponse)
async def list_units(
    property_id: str,
    status: str | None = None,
    ps: PropertyStore = Depends(get_property_store),
) -> UnitListResponse:
    prop = await ps.get_property(property_id)
    if not prop:
        raise HTTPException(404, f"Property '{property_id}' not found")
    unit_status = UnitStatus(status) if status else None
    units = await ps.list_units(property_id=property_id, status=unit_status)
    return UnitListResponse(
        property_id=property_id,
        count=len(units),
        units=[u.model_dump(mode="json") for u in units],
    )


@router.get("/{property_id}/rent-roll", response_model=RentRollResponse)
async def rent_roll(
    property_id: str,
    svc: RentRollService = Depends(get_rent_roll_service),
) -> RentRollResponse:
    result = await svc.build_rent_roll(property_id)
    if result is None:
        raise HTTPException(404, f"Property '{property_id}' not found")
    return RentRollResponse(**result.model_dump())


class UpdatePropertyRequest(BaseModel):
    name: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    portfolio_id: str | None = None


@router.patch("/{property_id}")
async def update_property(
    property_id: str,
    body: UpdatePropertyRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> dict[str, str]:
    prop = await ps.get_property(property_id)
    if not prop:
        raise HTTPException(404, f"Property '{property_id}' not found")

    updates: dict[str, object] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.portfolio_id is not None:
        updates["portfolio_id"] = body.portfolio_id
    if any(f is not None for f in (body.street, body.city, body.state, body.zip_code)):
        updates["address"] = Address(
            street=body.street or prop.address.street,
            city=body.city or prop.address.city,
            state=body.state or prop.address.state,
            zip_code=body.zip_code or prop.address.zip_code,
        )

    updated = prop.model_copy(update=updates)
    await ps.upsert_property(updated)
    return {"id": property_id, "name": updated.name}


@router.delete("/{property_id}", status_code=200)
async def delete_property(
    property_id: str,
    ps: PropertyStore = Depends(get_property_store),
) -> dict[str, bool]:
    deleted = await ps.delete_property(property_id)
    if not deleted:
        raise HTTPException(404, f"Property '{property_id}' not found")
    return {"deleted": True}
