"""REST endpoints for tenant queries."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from remi.application.api.shared_schemas import DeletedResponse, UpdatedResponse
from remi.application.portfolio import TenantDetail
from remi.shell.api.dependencies import Ctr
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/tenants", tags=["tenants"])


class UpdateTenantRequest(BaseModel):
    email: str | None = None
    phone: str | None = None


@router.get("/{tenant_id}", response_model=TenantDetail)
async def get_tenant(
    tenant_id: str,
    c: Ctr,
) -> TenantDetail:
    detail = await c.tenant_resolver.get_tenant_detail(tenant_id)
    if not detail:
        raise NotFoundError("Tenant", tenant_id)
    return detail


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    body: UpdateTenantRequest,
    c: Ctr,
) -> UpdatedResponse:
    tenant = await c.property_store.get_tenant(tenant_id)
    if not tenant:
        raise NotFoundError("Tenant", tenant_id)

    updates: dict[str, str | None] = {}
    if body.email is not None:
        updates["email"] = body.email
    if body.phone is not None:
        updates["phone"] = body.phone

    updated = tenant.model_copy(update=updates)
    await c.property_store.upsert_tenant(updated)
    return UpdatedResponse(id=tenant_id, name=updated.name)


@router.delete("/{tenant_id}", status_code=200)
async def delete_tenant(
    tenant_id: str,
    c: Ctr,
) -> DeletedResponse:
    deleted = await c.property_store.delete_tenant(tenant_id)
    if not deleted:
        raise NotFoundError("Tenant", tenant_id)
    return DeletedResponse()
