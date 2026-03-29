"""REST endpoints for property managers (director-level review)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from remi.domain.properties.models import Portfolio, PropertyManager
from remi.infrastructure.config.container import Container
from remi.interfaces.api.dependencies import get_container
from remi.interfaces.api.managers.schemas import (
    AssignPropertiesRequest,
    AssignPropertiesResponse,
    CreateManagerRequest,
    CreateManagerResponse,
    ManagerListItem,
    ManagerListResponse,
    ManagerReviewResponse,
)

router = APIRouter(prefix="/managers", tags=["managers"])


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9:]+", "-", text.lower().strip()).strip("-")


@router.get("", response_model=ManagerListResponse)
async def list_managers(
    container: Container = Depends(get_container),
) -> ManagerListResponse:
    summaries = await container.manager_review.list_manager_summaries()
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
            )
            for s in summaries
        ]
    )


@router.get("/{manager_id}/review", response_model=ManagerReviewResponse)
async def manager_review(
    manager_id: str,
    container: Container = Depends(get_container),
) -> ManagerReviewResponse:
    result = await container.manager_review.aggregate_manager(manager_id)
    if not result:
        raise HTTPException(404, f"Manager '{manager_id}' not found")
    return ManagerReviewResponse(**result.model_dump())


@router.post("", response_model=CreateManagerResponse, status_code=201)
async def create_manager(
    body: CreateManagerRequest,
    container: Container = Depends(get_container),
) -> CreateManagerResponse:
    manager_id = _slugify(f"manager:{body.name}")
    portfolio_id = _slugify(f"portfolio:{body.name}")

    existing = await container.property_store.get_manager(manager_id)
    if existing:
        raise HTTPException(409, f"Manager '{body.name}' already exists (id={manager_id})")

    await container.property_store.upsert_manager(PropertyManager(
        id=manager_id,
        name=body.name,
        email=body.email,
        company=body.company,
        phone=body.phone,
    ))
    await container.property_store.upsert_portfolio(Portfolio(
        id=portfolio_id,
        manager_id=manager_id,
        name=f"{body.name} Portfolio",
    ))

    return CreateManagerResponse(
        manager_id=manager_id,
        portfolio_id=portfolio_id,
        name=body.name,
    )


@router.post(
    "/{manager_id}/assign",
    response_model=AssignPropertiesResponse,
)
async def assign_properties(
    manager_id: str,
    body: AssignPropertiesRequest,
    container: Container = Depends(get_container),
) -> AssignPropertiesResponse:
    mgr = await container.property_store.get_manager(manager_id)
    if not mgr:
        raise HTTPException(404, f"Manager '{manager_id}' not found")

    portfolios = await container.property_store.list_portfolios(manager_id=manager_id)
    if not portfolios:
        raise HTTPException(400, f"Manager '{manager_id}' has no portfolio")
    portfolio_id = portfolios[0].id

    assigned = 0
    already = 0
    not_found: list[str] = []

    for pid in body.property_ids:
        prop = await container.property_store.get_property(pid)
        if not prop:
            not_found.append(pid)
            continue
        if prop.portfolio_id == portfolio_id:
            already += 1
            continue
        updated = prop.model_copy(update={"portfolio_id": portfolio_id})
        await container.property_store.upsert_property(updated)
        assigned += 1

    return AssignPropertiesResponse(
        manager_id=manager_id,
        assigned=assigned,
        already_assigned=already,
        not_found=not_found,
    )
