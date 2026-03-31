"""Dashboard REST endpoints — pure PropertyStore aggregation views."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query

from remi.application.dashboard.service import (
    DelinquencyBoard,
    LeaseCalendar,
    PortfolioOverview,
    RentRollView,
    VacancyTracker,
)
from remi.domain.properties.models import Portfolio, PropertyManager
from remi.interfaces.api.dependencies import get_container

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9:]+", "-", text.lower().strip()).strip("-")


def _manager_name_from_tag(tag: str) -> str:
    suffixes = ("management", "mgmt", "properties", "property")
    name = tag.strip()
    lower = name.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name or tag

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _get_dashboard(container: Container):  # noqa: ANN202
    return container.dashboard_service


@router.get("/overview", response_model=PortfolioOverview)
async def overview(
    manager_id: str | None = None,
    container: Container = Depends(get_container),
) -> PortfolioOverview:
    svc = _get_dashboard(container)
    return await svc.portfolio_overview(manager_id=manager_id)


@router.get("/delinquency", response_model=DelinquencyBoard)
async def delinquency(
    manager_id: str | None = None,
    container: Container = Depends(get_container),
) -> DelinquencyBoard:
    svc = _get_dashboard(container)
    return await svc.delinquency_board(manager_id=manager_id)


@router.get("/leases/expiring", response_model=LeaseCalendar)
async def leases_expiring(
    days: int = 90,
    manager_id: str | None = None,
    container: Container = Depends(get_container),
) -> LeaseCalendar:
    svc = _get_dashboard(container)
    return await svc.lease_expiration_calendar(days=days, manager_id=manager_id)


@router.get("/rent-roll/{property_id}", response_model=RentRollView)
async def rent_roll(
    property_id: str,
    container: Container = Depends(get_container),
) -> RentRollView:
    svc = _get_dashboard(container)
    result = await svc.rent_roll(property_id)
    if result is None:
        raise HTTPException(404, f"Property '{property_id}' not found")
    return result


@router.get("/vacancies", response_model=VacancyTracker)
async def vacancies(
    manager_id: str | None = None,
    container: Container = Depends(get_container),
) -> VacancyTracker:
    svc = _get_dashboard(container)
    return await svc.vacancy_tracker(manager_id=manager_id)


@router.get("/needs-manager")
async def needs_manager(
    container: Container = Depends(get_container),
) -> dict:
    """Properties that haven't been assigned to a manager yet.

    These will resolve automatically as the director continues uploading
    reports — either per-manager uploads or bulk reports that contain
    the manager tag.
    """
    all_props = await container.property_store.list_properties()
    items = [
        {"id": p.id, "name": p.name, "address": p.address.one_line()}
        for p in all_props
        if not p.portfolio_id
    ]
    return {"total": len(items), "properties": items}


@router.get("/snapshots")
async def snapshots(
    manager_id: str | None = Query(default=None),
    container: Container = Depends(get_container),
) -> dict:
    """Performance snapshots for trend tracking."""
    history = container.snapshot_service.get_history(manager_id=manager_id)
    return {"total": len(history), "snapshots": [s.model_dump() for s in history]}


@router.post("/snapshots/capture")
async def capture_snapshot(
    container: Container = Depends(get_container),
) -> dict:
    """Manually trigger a performance snapshot (also auto-triggered after uploads)."""
    batch = await container.snapshot_service.capture()
    return {"captured": len(batch)}


@router.post("/auto-assign")
async def auto_assign(
    container: Container = Depends(get_container),
) -> dict:
    """Auto-assign unassigned properties to managers using manager_tag stored
    in the knowledge graph during lease expiration ingestion.

    Walks every unassigned property (portfolio_id == ""), looks it up across
    all knowledge store namespaces for an appfolio_property entity that carries
    a manager_tag, then creates the manager/portfolio if needed and assigns the
    property. Returns counts of what was assigned and what remains unresolved.
    """
    ps = container.property_store
    ks = container.knowledge_store

    # Collect all unassigned properties
    all_props = await ps.list_properties()
    unassigned = [p for p in all_props if not p.portfolio_id]

    if not unassigned:
        return {"assigned": 0, "unresolved": 0, "message": "Nothing to assign"}

    # Build a lookup: property_id -> manager_tag by scanning all knowledge namespaces
    # The knowledge store entities are keyed by namespace then entity_id.
    # InMemoryKnowledgeStore exposes _entities directly; we iterate it safely.
    prop_to_tag: dict[str, str] = {}
    kb_entities = getattr(ks, "_entities", {})
    for _ns, entities in kb_entities.items():
        for entity_id, entity in entities.items():
            if entity.entity_type == "appfolio_property":
                tag = entity.properties.get("manager_tag", "")
                if tag and tag.lower() not in ("month-to-month", ""):
                    # entity_id matches the property_id slug (e.g. "property:100-smithfield-st")
                    if entity_id not in prop_to_tag:
                        prop_to_tag[entity_id] = tag

    # Cache for manager/portfolio creation so we don't repeat DB calls per property
    portfolio_cache: dict[str, str] = {}  # manager_tag -> portfolio_id

    async def _ensure_manager_cached(tag: str) -> str:
        if tag in portfolio_cache:
            return portfolio_cache[tag]
        mgr_name = _manager_name_from_tag(tag)
        manager_id = _slugify(f"manager:{mgr_name}")
        await ps.upsert_manager(PropertyManager(
            id=manager_id,
            name=mgr_name,
            manager_tag=tag,
        ))
        portfolio_id = _slugify(f"portfolio:{mgr_name}")
        await ps.upsert_portfolio(Portfolio(
            id=portfolio_id,
            manager_id=manager_id,
            name=f"{mgr_name} Portfolio",
        ))
        portfolio_cache[tag] = portfolio_id
        return portfolio_id

    assigned = 0
    unresolved = 0

    for prop in unassigned:
        tag = prop_to_tag.get(prop.id, "")
        if not tag:
            unresolved += 1
            continue
        portfolio_id = await _ensure_manager_cached(tag)
        updated = prop.model_copy(update={"portfolio_id": portfolio_id})
        await ps.upsert_property(updated)
        assigned += 1

    # Capture a fresh snapshot so Performance tab reflects the new assignments
    with contextlib.suppress(Exception):
        await container.snapshot_service.capture()

    return {
        "assigned": assigned,
        "unresolved": unresolved,
        "message": f"Assigned {assigned} properties from knowledge store tags. {unresolved} had no tag and remain unassigned.",
    }
