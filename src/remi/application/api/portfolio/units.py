"""REST endpoints for cross-property unit queries."""

from __future__ import annotations

from fastapi import APIRouter

from remi.application.portfolio import UnitListResult
from remi.shell.api.dependencies import Ctr

router = APIRouter(prefix="/units", tags=["units"])


@router.get("", response_model=UnitListResult)
async def list_all_units(
    c: Ctr,
    property_id: str | None = None,
    status: str | None = None,
) -> UnitListResult:
    return await c.unit_resolver.list_units(property_id=property_id, status=status)
