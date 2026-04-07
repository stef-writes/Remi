"""REST endpoints for property managers (director-level review)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel

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
from remi.application.core.models import (
    ActionItemStatus,
    MeetingBrief,
    PropertyManager,
)
from remi.application.views import ManagerSummary
from remi.shell.api.dependencies import Ctr
from remi.types.errors import ConflictError, DomainError, NotFoundError
from remi.types.identity import manager_id as _manager_id

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/managers", tags=["managers"])


@router.get("", response_model=ManagerListResponse)
async def list_managers(c: Ctr) -> ManagerListResponse:
    summaries = await c.manager_resolver.list_manager_summaries()
    return ManagerListResponse(managers=summaries)


@router.get("/rankings", response_model=ManagerRankingsResponse)
async def manager_rankings(
    c: Ctr,
    sort_by: str = Query(default="delinquency_rate", description="Field to sort by"),
    ascending: bool = Query(default=False, description="Sort ascending"),
    limit: int | None = Query(default=None, ge=1, description="Max results"),
) -> ManagerRankingsResponse:
    rows = await c.manager_resolver.rank_managers(
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
    result = await c.manager_resolver.aggregate_manager(manager_id)
    if not result:
        raise NotFoundError("Manager", manager_id)
    return result


class MeetingBriefRequest(BaseModel):
    focus: str | None = None


def _snapshot_hash(pipeline_input: str) -> str:
    """Deterministic hash of the portfolio data fed to the pipeline."""
    return hashlib.sha256(pipeline_input.encode()).hexdigest()[:16]


def _brief_response(brief: MeetingBrief) -> dict[str, Any]:
    return {
        "id": brief.id,
        "manager_id": brief.manager_id,
        "snapshot_hash": brief.snapshot_hash,
        "brief": brief.brief,
        "analysis": brief.analysis,
        "focus": brief.focus,
        "generated_at": brief.generated_at.isoformat(),
        "usage": {
            "prompt_tokens": brief.prompt_tokens,
            "completion_tokens": brief.completion_tokens,
        },
    }


async def _build_pipeline_input(
    c: Ctr,
    manager_id: str,
    review: ManagerSummary,
    focus: str | None,
) -> str:
    delinquency, leases, vacancies, action_items, notes = await asyncio.gather(
        c.dashboard_resolver.delinquency_board(manager_id=manager_id),
        c.dashboard_resolver.lease_expiration_calendar(days=90, manager_id=manager_id),
        c.dashboard_resolver.vacancy_tracker(manager_id=manager_id),
        c.property_store.list_action_items(
            manager_id=manager_id,
            status=ActionItemStatus.OPEN,
        ),
        c.property_store.list_notes(
            entity_type="PropertyManager",
            entity_id=manager_id,
        ),
    )

    recent_notes = sorted(notes, key=lambda n: n.created_at, reverse=True)[:10]

    return json.dumps(
        {
            "manager": {
                "name": review.name,
                "email": review.email,
                "company": review.company,
            },
            "metrics": {
                **review.metrics.model_dump(mode="json"),
                "emergency_maintenance": review.emergency_maintenance,
                "expired_leases": review.expired_leases,
                "below_market_units": review.below_market_units,
                "delinquent_count": review.delinquent_count,
                "total_delinquent_balance": review.total_delinquent_balance,
            },
            "properties": [p.model_dump(mode="json") for p in review.properties],
            "delinquency": delinquency.model_dump(mode="json"),
            "leases": leases.model_dump(mode="json"),
            "vacancies": vacancies.model_dump(mode="json"),
            "existing_actions": [
                {"title": a.title, "status": a.status.value, "priority": a.priority.value}
                for a in action_items
            ],
            "notes": [
                {"content": n.content, "created_at": n.created_at.isoformat()}
                for n in recent_notes
            ],
            "focus": focus,
        },
        default=str,
    )


@router.post("/{manager_id}/meeting-brief")
async def generate_meeting_brief(
    manager_id: str,
    c: Ctr,
    body: MeetingBriefRequest | None = None,
) -> dict[str, Any]:
    """Generate an LLM-powered meeting brief and persist it."""
    review = await c.manager_resolver.aggregate_manager(manager_id)
    if not review:
        raise NotFoundError("Manager", manager_id)

    focus = body.focus if body else None
    pipeline_input = await _build_pipeline_input(c, manager_id, review, focus)
    snap_hash = _snapshot_hash(pipeline_input)

    logger.info(
        "meeting_brief_start",
        manager_id=manager_id,
        snapshot_hash=snap_hash,
        input_length=len(pipeline_input),
    )

    from remi.agent.workflow import load_workflow

    workflow_def = load_workflow("manager_review")
    result = await c.workflow_runner.run(workflow_def, pipeline_input)

    analysis = result.step("analyze")
    brief_data = result.step("brief")

    if not brief_data or not isinstance(brief_data, dict):
        logger.warning(
            "meeting_brief_empty",
            manager_id=manager_id,
            analysis_type=type(analysis).__name__,
            brief_type=type(brief_data).__name__,
        )
        raise DomainError("Failed to generate meeting brief — LLM returned empty result")

    brief = MeetingBrief(
        id=f"brief:{uuid.uuid4().hex[:12]}",
        manager_id=manager_id,
        snapshot_hash=snap_hash,
        brief=brief_data,
        analysis=analysis if isinstance(analysis, dict) else {},
        focus=focus,
        prompt_tokens=result.total_usage.prompt_tokens,
        completion_tokens=result.total_usage.completion_tokens,
    )

    await c.property_store.upsert_meeting_brief(brief)

    logger.info(
        "meeting_brief_persisted",
        brief_id=brief.id,
        manager_id=manager_id,
        snapshot_hash=snap_hash,
    )

    return _brief_response(brief)


@router.get("/{manager_id}/meeting-briefs")
async def list_meeting_briefs(
    manager_id: str,
    c: Ctr,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """List past meeting briefs for a manager, newest first."""
    mgr = await c.property_store.get_manager(manager_id)
    if not mgr:
        raise NotFoundError("Manager", manager_id)

    briefs = await c.property_store.list_meeting_briefs(
        manager_id=manager_id,
        limit=limit,
    )

    # Compute the current snapshot hash so the frontend can detect staleness
    review = await c.manager_resolver.aggregate_manager(manager_id)
    current_hash: str | None = None
    if review:
        pipeline_input = await _build_pipeline_input(c, manager_id, review, focus=None)
        current_hash = _snapshot_hash(pipeline_input)

    return {
        "briefs": [_brief_response(b) for b in briefs],
        "total": len(briefs),
        "current_snapshot_hash": current_hash,
    }


@router.post("", response_model=CreateManagerResponse, status_code=201)
async def create_manager(
    body: CreateManagerRequest,
    c: Ctr,
) -> CreateManagerResponse:
    manager_id = _manager_id(body.name)

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

    return CreateManagerResponse(
        manager_id=manager_id,
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

    return CreateManagerResponse(
        manager_id=manager_id,
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

    source_props = await ps.list_properties(manager_id=body.source_manager_id)
    moved = 0
    for prop in source_props:
        updated = prop.model_copy(update={"manager_id": body.target_manager_id})
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

    summary_task = c.manager_resolver.aggregate_manager(manager_id)
    sig_task = c.signal_store.list_signals(scope={"manager_id": manager_id})
    ev_task = c.event_store.list_recent(limit=20)

    summary, sigs, changesets = await asyncio.gather(
        summary_task,
        sig_task,
        ev_task,
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

    assigned = 0
    already = 0
    not_found: list[str] = []

    for pid in body.property_ids:
        prop = await ps.get_property(pid)
        if not prop:
            not_found.append(pid)
            continue
        if prop.manager_id == manager_id:
            already += 1
            continue
        updated = prop.model_copy(update={"manager_id": manager_id})
        await ps.upsert_property(updated)
        assigned += 1

    return AssignPropertiesResponse(
        manager_id=manager_id,
        assigned=assigned,
        already_assigned=already,
        not_found=not_found,
    )
