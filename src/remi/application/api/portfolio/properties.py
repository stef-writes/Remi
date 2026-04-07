"""REST endpoints for properties and units."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from remi.application.api.schemas import (
    CreatePropertyRequest,
    CreatePropertyResponse,
    PropertyDetail,
    PropertyListResponse,
    UnitListResponse,
    UpdatePropertyRequest,
)
from remi.application.api.shared_schemas import DeletedResponse, UpdatedResponse
from remi.application.core.models import Address, Property, PropertyType
from remi.application.views import (
    RentRollResult,
)
from remi.shell.api.dependencies import Ctr
from remi.types.errors import NotFoundError
from remi.types.identity import property_id as _property_id

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=PropertyListResponse)
async def list_properties(
    c: Ctr,
    manager_id: str | None = None,
    owner_id: str | None = None,
) -> PropertyListResponse:
    items = await c.property_resolver.list_properties(
        manager_id=manager_id,
        owner_id=owner_id,
    )
    return PropertyListResponse(properties=items)


@router.post("", response_model=CreatePropertyResponse, status_code=201)
async def create_property(
    body: CreatePropertyRequest,
    c: Ctr,
) -> CreatePropertyResponse:
    pid = _property_id(body.name)
    prop = Property(
        id=pid,
        manager_id=body.manager_id,
        owner_id=body.owner_id,
        name=body.name,
        address=Address(
            street=body.street,
            city=body.city,
            state=body.state,
            zip_code=body.zip_code,
        ),
        property_type=PropertyType(body.property_type),
        year_built=body.year_built,
    )
    await c.property_store.upsert_property(prop)
    return CreatePropertyResponse(
        property_id=pid,
        name=body.name,
    )


@router.get("/{property_id}", response_model=PropertyDetail)
async def get_property(
    property_id: str,
    c: Ctr,
) -> PropertyDetail:
    detail = await c.property_resolver.get_property_detail(property_id)
    if not detail:
        raise NotFoundError("Property", property_id)
    return detail


@router.get("/{property_id}/units", response_model=UnitListResponse)
async def list_units(
    property_id: str,
    c: Ctr,
    status: str | None = None,
) -> UnitListResponse:
    detail = await c.property_resolver.get_property_detail(property_id)
    if not detail:
        raise NotFoundError("Property", property_id)
    units = detail.units
    if status:
        units = [u for u in units if u.status == status]
    return UnitListResponse(
        property_id=property_id,
        count=len(units),
        units=units,
    )


@router.get("/{property_id}/rent-roll", response_model=RentRollResult)
async def rent_roll(
    property_id: str,
    c: Ctr,
) -> RentRollResult:
    result = await c.rent_roll_resolver.build_rent_roll(property_id)
    if result is None:
        raise NotFoundError("Property", property_id)
    return result


@router.patch("/{property_id}")
async def update_property(
    property_id: str,
    body: UpdatePropertyRequest,
    c: Ctr,
) -> UpdatedResponse:
    prop = await c.property_store.get_property(property_id)
    if not prop:
        raise NotFoundError("Property", property_id)

    updates: dict[str, object] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.manager_id is not None:
        updates["manager_id"] = body.manager_id or None
    if body.owner_id is not None:
        updates["owner_id"] = body.owner_id or None
    if any(f is not None for f in (body.street, body.city, body.state, body.zip_code)):
        updates["address"] = Address(
            street=body.street or prop.address.street,
            city=body.city or prop.address.city,
            state=body.state or prop.address.state,
            zip_code=body.zip_code or prop.address.zip_code,
        )

    updated = prop.model_copy(update=updates)
    await c.property_store.upsert_property(updated)
    return UpdatedResponse(id=property_id, name=updated.name)


@router.get("/{property_id}/context")
async def property_context(
    property_id: str,
    c: Ctr,
) -> dict[str, Any]:
    """Composite context for a property — one call for the frontend detail page."""
    import asyncio

    detail = await c.property_resolver.get_property_detail(property_id)
    if not detail:
        raise NotFoundError("Property", property_id)

    rr_task = c.rent_roll_resolver.build_rent_roll(property_id)
    sig_task = c.signal_store.list_signals(scope={"property_id": property_id})
    ev_task = c.event_store.list_by_entity(property_id, limit=20)
    maint_task = c.maintenance_resolver.maintenance_summary(property_id=property_id)

    rr, sigs, changesets, maint = await asyncio.gather(
        rr_task,
        sig_task,
        ev_task,
        maint_task,
    )

    from remi.application.api.intelligence.signal_schemas import SignalSummary

    return {
        "property": detail.model_dump(mode="json"),
        "rent_roll": rr.model_dump(mode="json") if rr else None,
        "signals": [
            SignalSummary(
                signal_id=s.signal_id,
                signal_type=s.signal_type,
                severity=s.severity.value,
                entity_type=s.entity_type,
                entity_id=s.entity_id,
                entity_name=s.entity_name,
                description=s.description,
                detected_at=s.detected_at.isoformat(),
            ).model_dump(mode="json")
            for s in sigs
        ],
        "recent_events": len(changesets),
        "maintenance": maint.model_dump(mode="json"),
    }


@router.delete("/{property_id}", status_code=200)
async def delete_property(
    property_id: str,
    c: Ctr,
) -> DeletedResponse:
    deleted = await c.property_store.delete_property(property_id)
    if not deleted:
        raise NotFoundError("Property", property_id)
    return DeletedResponse()
