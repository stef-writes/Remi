"""REST endpoints for properties and units."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from remi.api.dependencies import get_property_query, get_property_store, get_rent_roll_service
from remi.api.properties.schemas import (
    PropertyDetail,
    PropertyListItem,
    PropertyListResponse,
    RentRollResponse,
    UnitListResponse,
    UnitSummary,
)
from remi.models.properties import PropertyStore, UnitStatus
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
