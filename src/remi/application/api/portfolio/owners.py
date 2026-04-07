"""Owners — read endpoint for the view-mode picker and owner detail."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from remi.shell.api.dependencies import Ctr

router = APIRouter(prefix="/owners", tags=["portfolio"])


class OwnerListItem(BaseModel):
    id: str
    name: str
    owner_type: str
    company: str | None
    email: str
    phone: str | None
    property_count: int


@router.get("", response_model=list[OwnerListItem])
async def list_owners(c: Ctr) -> list[OwnerListItem]:
    owners = await c.property_store.list_owners()
    all_props = await c.property_store.list_properties()
    props_by_owner: dict[str, int] = {}
    for p in all_props:
        if p.owner_id:
            props_by_owner[p.owner_id] = props_by_owner.get(p.owner_id, 0) + 1
    return [
        OwnerListItem(
            id=o.id,
            name=o.name,
            owner_type=o.owner_type.value,
            company=o.company,
            email=o.email,
            phone=o.phone,
            property_count=props_by_owner.get(o.id, 0),
        )
        for o in owners
    ]
