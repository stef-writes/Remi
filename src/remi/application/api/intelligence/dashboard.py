"""Dashboard REST endpoints — pure PropertyStore aggregation views."""

from __future__ import annotations

from fastapi import APIRouter

from remi.application.views import (
    AutoAssignResult,
    DashboardOverview,
    DelinquencyBoard,
    DelinquencyTrend,
    LeaseCalendar,
    MaintenanceTrend,
    NeedsManagerResult,
    OccupancyTrend,
    RentRollResult,
    RentTrend,
    VacancyTracker,
    property_ids_for_owner,
)
from remi.shell.api.dependencies import Ctr
from remi.types.errors import NotFoundError

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
async def overview(
    c: Ctr,
    manager_id: str | None = None,
    owner_id: str | None = None,
) -> DashboardOverview:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.dashboard_overview(manager_id=manager_id, property_ids=pids)


@router.get("/delinquency", response_model=DelinquencyBoard)
async def delinquency(
    c: Ctr,
    manager_id: str | None = None,
    owner_id: str | None = None,
) -> DelinquencyBoard:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.delinquency_board(manager_id=manager_id, property_ids=pids)


@router.get("/leases/expiring", response_model=LeaseCalendar)
async def leases_expiring(
    c: Ctr,
    days: int = 90,
    manager_id: str | None = None,
    owner_id: str | None = None,
) -> LeaseCalendar:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.lease_expiration_calendar(
        days=days, manager_id=manager_id, property_ids=pids
    )


@router.get("/rent-roll/{property_id}", response_model=RentRollResult)
async def rent_roll(
    property_id: str,
    c: Ctr,
) -> RentRollResult:
    result = await c.rent_roll_resolver.build_rent_roll(property_id)
    if result is None:
        raise NotFoundError("Property", property_id)
    return result


@router.get("/vacancies", response_model=VacancyTracker)
async def vacancies(
    c: Ctr,
    manager_id: str | None = None,
    owner_id: str | None = None,
) -> VacancyTracker:
    pids = await property_ids_for_owner(c.property_store, owner_id) if owner_id else None
    return await c.dashboard_resolver.vacancy_tracker(manager_id=manager_id, property_ids=pids)


@router.get("/needs-manager", response_model=NeedsManagerResult)
async def needs_manager(c: Ctr) -> NeedsManagerResult:
    return await c.dashboard_resolver.needs_manager()


@router.get("/trends/delinquency", response_model=DelinquencyTrend)
async def delinquency_trend(
    c: Ctr,
    manager_id: str | None = None,
    property_id: str | None = None,
    periods: int = 12,
) -> DelinquencyTrend:
    return await c.dashboard_resolver.delinquency_trend(
        manager_id=manager_id, property_id=property_id, periods=periods
    )


@router.get("/trends/occupancy", response_model=OccupancyTrend)
async def occupancy_trend(
    c: Ctr,
    manager_id: str | None = None,
    property_id: str | None = None,
    periods: int = 12,
) -> OccupancyTrend:
    return await c.dashboard_resolver.occupancy_trend(
        manager_id=manager_id, property_id=property_id, periods=periods
    )


@router.get("/trends/rent", response_model=RentTrend)
async def rent_trend(
    c: Ctr,
    manager_id: str | None = None,
    property_id: str | None = None,
    periods: int = 12,
) -> RentTrend:
    return await c.dashboard_resolver.rent_trend(
        manager_id=manager_id, property_id=property_id, periods=periods
    )


@router.get("/trends/maintenance", response_model=MaintenanceTrend)
async def maintenance_trend(
    c: Ctr,
    manager_id: str | None = None,
    property_id: str | None = None,
    unit_id: str | None = None,
    periods: int = 12,
) -> MaintenanceTrend:
    return await c.dashboard_resolver.maintenance_trend(
        manager_id=manager_id,
        property_id=property_id,
        unit_id=unit_id,
        periods=periods,
    )


@router.post("/auto-assign", response_model=AutoAssignResult)
async def auto_assign(c: Ctr) -> AutoAssignResult:
    return await c.auto_assign_service.auto_assign()
