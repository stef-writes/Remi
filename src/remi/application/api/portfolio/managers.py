"""REST endpoints for property managers (director-level review)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from remi.application.api.schemas import (
    AssignPropertiesRequest,
    AssignPropertiesResponse,
    CreateManagerRequest,
    CreateManagerResponse,
    ManagerListResponse,
    ManagerRankingsResponse,
    MergeManagersRequest,
    MergeManagersResponse,
    UpdateManagerRequest,
)
from remi.application.api.shared_schemas import DeletedResponse
from remi.application.core.models import Portfolio, PropertyManager
from remi.application.portfolio import ManagerSummary
from remi.shell.api.dependencies import Ctr
from remi.types.errors import ConflictError, DomainError, NotFoundError
from remi.types.text import slugify as _slugify

router = APIRouter(prefix="/managers", tags=["managers"])


@router.get("", response_model=ManagerListResponse)
async def list_managers(c: Ctr) -> ManagerListResponse:
    summaries = await c.manager_review.list_manager_summaries()
    return ManagerListResponse(managers=summaries)


@router.get("/rankings", response_model=ManagerRankingsResponse)
async def manager_rankings(
    c: Ctr,
    sort_by: str = Query(default="delinquency_rate", description="Field to sort by"),
    ascending: bool = Query(default=False, description="Sort ascending"),
    limit: int | None = Query(default=None, ge=1, description="Max results"),
) -> ManagerRankingsResponse:
    rows = await c.manager_review.rank_managers(
        sort_by=sort_by,
        ascending=ascending,
        limit=limit,
    )
    return ManagerRankingsResponse(rankings=rows, total=len(rows), sort_by=sort_by)


@router.get("/{manager_id}/review", response_model=ManagerSummary)
async def manager_review(
    manager_id: str,
    c: Ctr,
) -> ManagerSummary:
    result = await c.manager_review.aggregate_manager(manager_id)
    if not result:
        raise NotFoundError("Manager", manager_id)
    return result


@router.post("", response_model=CreateManagerResponse, status_code=201)
async def create_manager(
    body: CreateManagerRequest,
    c: Ctr,
) -> CreateManagerResponse:
    manager_id = _slugify(f"manager:{body.name}")
    portfolio_id = _slugify(f"portfolio:{body.name}")

    existing = await c.property_store.get_manager(manager_id)
    if existing:
        raise ConflictError(f"Manager '{body.name}' already exists (id={manager_id})")

    await c.property_store.upsert_manager(
        PropertyManager(
            id=manager_id,
            name=body.name,
            email=body.email,
            company=body.company,
            phone=body.phone,
        )
    )
    await c.property_store.upsert_portfolio(
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
    c: Ctr,
) -> CreateManagerResponse:
    mgr = await c.property_store.get_manager(manager_id)
    if not mgr:
        raise NotFoundError("Manager", manager_id)

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
    await c.property_store.upsert_manager(updated)

    portfolios = await c.property_store.list_portfolios(manager_id=manager_id)
    portfolio_id = portfolios[0].id if portfolios else ""

    return CreateManagerResponse(
        manager_id=manager_id,
        portfolio_id=portfolio_id,
        name=updated.name,
    )


@router.delete("/{manager_id}", status_code=200)
async def delete_manager(
    manager_id: str,
    c: Ctr,
) -> DeletedResponse:
    deleted = await c.property_store.delete_manager(manager_id)
    if not deleted:
        raise NotFoundError("Manager", manager_id)
    return DeletedResponse()


@router.post("/merge", response_model=MergeManagersResponse)
async def merge_managers(
    body: MergeManagersRequest,
    c: Ctr,
) -> MergeManagersResponse:
    """Move all properties from source manager to target, then delete source."""
    ps = c.property_store
    source = await ps.get_manager(body.source_manager_id)
    target = await ps.get_manager(body.target_manager_id)
    if not source:
        raise NotFoundError("Manager", body.source_manager_id)
    if not target:
        raise NotFoundError("Manager", body.target_manager_id)

    target_portfolios = await ps.list_portfolios(manager_id=body.target_manager_id)
    if not target_portfolios:
        raise DomainError("Target manager has no portfolio")
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


@router.get("/{manager_id}/context")
async def manager_context(
    manager_id: str,
    c: Ctr,
) -> dict[str, Any]:
    """Composite context for a manager — one call for the frontend manager page."""
    import asyncio

    from remi.application.api.intelligence.signal_schemas import SignalSummary

    summary_task = c.manager_review.aggregate_manager(manager_id)
    sig_task = c.signal_store.list_signals(scope={"manager_id": manager_id})
    ev_task = c.event_store.list_recent(limit=20)

    summary, sigs, changesets = await asyncio.gather(
        summary_task, sig_task, ev_task,
    )

    if summary is None:
        raise NotFoundError("Manager", manager_id)

    return {
        "manager": summary.model_dump(mode="json"),
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
    }


@router.post(
    "/{manager_id}/assign",
    response_model=AssignPropertiesResponse,
)
async def assign_properties(
    manager_id: str,
    body: AssignPropertiesRequest,
    c: Ctr,
) -> AssignPropertiesResponse:
    ps = c.property_store
    mgr = await ps.get_manager(manager_id)
    if not mgr:
        raise NotFoundError("Manager", manager_id)

    portfolios = await ps.list_portfolios(manager_id=manager_id)
    if not portfolios:
        raise DomainError(f"Manager '{manager_id}' has no portfolio")
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
