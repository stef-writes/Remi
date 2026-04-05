"""Dashboard REST endpoints — pure PropertyStore aggregation views."""

from __future__ import annotations

from fastapi import APIRouter

from remi.application.api.intelligence.dashboard_schemas import AutoAssignResponse
from remi.application.portfolio import (
    DelinquencyBoard,
    LeaseCalendar,
    NeedsManagerResult,
    PortfolioOverview,
    RentRollView,
    VacancyTracker,
)
from remi.shell.api.dependencies import Ctr
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=PortfolioOverview)
async def overview(
    c: Ctr,
    manager_id: str | None = None,
) -> PortfolioOverview:
    return await c.dashboard_service.portfolio_overview(manager_id=manager_id)


@router.get("/delinquency", response_model=DelinquencyBoard)
async def delinquency(
    c: Ctr,
    manager_id: str | None = None,
) -> DelinquencyBoard:
    return await c.dashboard_service.delinquency_board(manager_id=manager_id)


@router.get("/leases/expiring", response_model=LeaseCalendar)
async def leases_expiring(
    c: Ctr,
    days: int = 90,
    manager_id: str | None = None,
) -> LeaseCalendar:
    return await c.dashboard_service.lease_expiration_calendar(days=days, manager_id=manager_id)


@router.get("/rent-roll/{property_id}", response_model=RentRollView)
async def rent_roll(
    property_id: str,
    c: Ctr,
) -> RentRollView:
    result = await c.dashboard_service.rent_roll(property_id)
    if result is None:
        raise NotFoundError("Property", property_id)
    return result


@router.get("/vacancies", response_model=VacancyTracker)
async def vacancies(
    c: Ctr,
    manager_id: str | None = None,
) -> VacancyTracker:
    return await c.dashboard_service.vacancy_tracker(manager_id=manager_id)


@router.get("/needs-manager", response_model=NeedsManagerResult)
async def needs_manager(c: Ctr) -> NeedsManagerResult:
    return await c.dashboard_service.needs_manager()


@router.post("/auto-assign", response_model=AutoAssignResponse)
async def auto_assign(c: Ctr) -> AutoAssignResponse:
    result = await c.auto_assign_service.auto_assign()
    return AutoAssignResponse(
        assigned=result.assigned,
        unresolved=result.unresolved,
        tags_available=result.tags_available,
        message=result.message,
    )
