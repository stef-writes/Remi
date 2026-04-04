"""REST endpoints for properties and units."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from remi.application.services.queries import (
    PortfolioQueryService,
    RentRollResult,
    RentRollService,
)
from remi.application.api.schemas import (
    PropertyDetail,
    PropertyListResponse,
    UnitListResponse,
    UpdatePropertyRequest,
)
from remi.application.core.models import Address, UnitStatus
from remi.application.core.protocols import PropertyStore
from remi.application.api.dependencies import (
    get_portfolio_query,
    get_property_store,
    get_rent_roll_service,
)
from remi.application.api.shared_schemas import DeletedResponse, UpdatedResponse
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=PropertyListResponse)
async def list_properties(
    portfolio_id: str | None = None,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> PropertyListResponse:
    items = await svc.list_properties(portfolio_id=portfolio_id)
    return PropertyListResponse(properties=items)


@router.get("/{property_id}", response_model=PropertyDetail)
async def get_property(
    property_id: str,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> PropertyDetail:
    detail = await svc.get_property_detail(property_id)
    if not detail:
        raise NotFoundError("Property", property_id)
    return detail


@router.get("/{property_id}/units", response_model=UnitListResponse)
async def list_units(
    property_id: str,
    status: str | None = None,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> UnitListResponse:
    detail = await svc.get_property_detail(property_id)
    if not detail:
        raise NotFoundError("Property", property_id)
    units = detail.units
    if status:
        target = UnitStatus(status)
        units = [u for u in units if u.status == target.value]
    return UnitListResponse(
        property_id=property_id,
        count=len(units),
        units=units,
    )


@router.get("/{property_id}/rent-roll", response_model=RentRollResult)
async def rent_roll(
    property_id: str,
    svc: RentRollService = Depends(get_rent_roll_service),
) -> RentRollResult:
    result = await svc.build_rent_roll(property_id)
    if result is None:
        raise NotFoundError("Property", property_id)
    return result


@router.patch("/{property_id}")
async def update_property(
    property_id: str,
    body: UpdatePropertyRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> UpdatedResponse:
    prop = await ps.get_property(property_id)
    if not prop:
        raise NotFoundError("Property", property_id)

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
    return UpdatedResponse(id=property_id, name=updated.name)


@router.delete("/{property_id}", status_code=200)
async def delete_property(
    property_id: str,
    ps: PropertyStore = Depends(get_property_store),
) -> DeletedResponse:
    deleted = await ps.delete_property(property_id)
    if not deleted:
        raise NotFoundError("Property", property_id)
    return DeletedResponse()
