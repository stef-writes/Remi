"""REST endpoints for property managers (director-level review)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from remi.api.dependencies import get_manager_review, get_property_store
from remi.api.managers.schemas import (
    AssignPropertiesRequest,
    AssignPropertiesResponse,
    CreateManagerRequest,
    CreateManagerResponse,
    ManagerListItem,
    ManagerListResponse,
    ManagerReviewResponse,
    MergeManagersRequest,
    MergeManagersResponse,
    UpdateManagerRequest,
)
from remi.models.properties import Portfolio, PropertyManager, PropertyStore
from remi.services.manager_review import ManagerReviewService
from remi.shared.text import slugify as _slugify

router = APIRouter(prefix="/managers", tags=["managers"])


@router.get("", response_model=ManagerListResponse)
async def list_managers(
    review: ManagerReviewService = Depends(get_manager_review),
) -> ManagerListResponse:
    summaries = await review.list_manager_summaries()
    return ManagerListResponse(
        managers=[
            ManagerListItem(
                id=s.manager_id,
                name=s.name,
                email=s.email,
                company=s.company,
                portfolio_count=s.portfolio_count,
                property_count=s.property_count,
                total_units=s.total_units,
                occupied=s.occupied,
                vacant=s.vacant,
                occupancy_rate=s.occupancy_rate,
                total_actual_rent=s.total_actual_rent,
                total_loss_to_lease=s.total_loss_to_lease,
                total_vacancy_loss=s.total_vacancy_loss,
                open_maintenance=s.open_maintenance,
                emergency_maintenance=s.emergency_maintenance,
                expiring_leases_90d=s.expiring_leases_90d,
                expired_leases=s.expired_leases,
                below_market_units=s.below_market_units,
                delinquent_count=s.delinquent_count,
                total_delinquent_balance=s.total_delinquent_balance,
            )
            for s in summaries
        ]
    )


@router.get("/{manager_id}/review", response_model=ManagerReviewResponse)
async def manager_review(
    manager_id: str,
    review: ManagerReviewService = Depends(get_manager_review),
) -> ManagerReviewResponse:
    result = await review.aggregate_manager(manager_id)
    if not result:
        raise HTTPException(404, f"Manager '{manager_id}' not found")
    return ManagerReviewResponse(**result.model_dump())


@router.post("", response_model=CreateManagerResponse, status_code=201)
async def create_manager(
    body: CreateManagerRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> CreateManagerResponse:
    manager_id = _slugify(f"manager:{body.name}")
    portfolio_id = _slugify(f"portfolio:{body.name}")

    existing = await ps.get_manager(manager_id)
    if existing:
        raise HTTPException(409, f"Manager '{body.name}' already exists (id={manager_id})")

    await ps.upsert_manager(
        PropertyManager(
            id=manager_id,
            name=body.name,
            email=body.email,
            company=body.company,
            phone=body.phone,
        )
    )
    await ps.upsert_portfolio(
        Portfolio(
            id=portfolio_id,
            manager_id=manager_id,
            name=f"{body.name} Portfolio",
        )
    )

    return CreateManagerResponse(
        manager_id=manager_id,
        portfolio_id=portfolio_id,
        name=body.name,
    )


@router.patch("/{manager_id}", response_model=CreateManagerResponse)
async def update_manager(
    manager_id: str,
    body: UpdateManagerRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> CreateManagerResponse:
    mgr = await ps.get_manager(manager_id)
    if not mgr:
        raise HTTPException(404, f"Manager '{manager_id}' not found")

    updates: dict[str, str | None] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.email is not None:
        updates["email"] = body.email
    if body.company is not None:
        updates["company"] = body.company
    if body.phone is not None:
        updates["phone"] = body.phone

    updated = mgr.model_copy(update=updates)
    await ps.upsert_manager(updated)

    portfolios = await ps.list_portfolios(manager_id=manager_id)
    portfolio_id = portfolios[0].id if portfolios else ""

    return CreateManagerResponse(
        manager_id=manager_id,
        portfolio_id=portfolio_id,
        name=updated.name,
    )


@router.delete("/{manager_id}", status_code=200)
async def delete_manager(
    manager_id: str,
    ps: PropertyStore = Depends(get_property_store),
) -> dict[str, bool]:
    deleted = await ps.delete_manager(manager_id)
    if not deleted:
        raise HTTPException(404, f"Manager '{manager_id}' not found")
    return {"deleted": True}


@router.post("/merge", response_model=MergeManagersResponse)
async def merge_managers(
    body: MergeManagersRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> MergeManagersResponse:
    """Move all properties from source manager to target, then delete source."""
    source = await ps.get_manager(body.source_manager_id)
    target = await ps.get_manager(body.target_manager_id)
    if not source:
        raise HTTPException(404, f"Source manager '{body.source_manager_id}' not found")
    if not target:
        raise HTTPException(404, f"Target manager '{body.target_manager_id}' not found")

    target_portfolios = await ps.list_portfolios(manager_id=body.target_manager_id)
    if not target_portfolios:
        raise HTTPException(400, f"Target manager has no portfolio")
    target_pf_id = target_portfolios[0].id

    source_portfolios = await ps.list_portfolios(manager_id=body.source_manager_id)
    moved = 0
    for spf in source_portfolios:
        props = await ps.list_properties(portfolio_id=spf.id)
        for prop in props:
            updated = prop.model_copy(update={"portfolio_id": target_pf_id})
            await ps.upsert_property(updated)
            moved += 1

    deleted = await ps.delete_manager(body.source_manager_id)

    return MergeManagersResponse(
        target_manager_id=body.target_manager_id,
        properties_moved=moved,
        source_deleted=deleted,
    )


@router.post(
    "/{manager_id}/assign",
    response_model=AssignPropertiesResponse,
)
async def assign_properties(
    manager_id: str,
    body: AssignPropertiesRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> AssignPropertiesResponse:
    mgr = await ps.get_manager(manager_id)
    if not mgr:
        raise HTTPException(404, f"Manager '{manager_id}' not found")

    portfolios = await ps.list_portfolios(manager_id=manager_id)
    if not portfolios:
        raise HTTPException(400, f"Manager '{manager_id}' has no portfolio")
    portfolio_id = portfolios[0].id

    assigned = 0
    already = 0
    not_found: list[str] = []

    for pid in body.property_ids:
        prop = await ps.get_property(pid)
        if not prop:
            not_found.append(pid)
            continue
        if prop.portfolio_id == portfolio_id:
            already += 1
            continue
        updated = prop.model_copy(update={"portfolio_id": portfolio_id})
        await ps.upsert_property(updated)
        assigned += 1

    return AssignPropertiesResponse(
        manager_id=manager_id,
        assigned=assigned,
        already_assigned=already,
        not_found=not_found,
    )
