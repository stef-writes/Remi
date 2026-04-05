"""REST endpoints for entailed signals."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter

from remi.agent.signals import Signal
from remi.application.api.intelligence.signal_schemas import (
    FeedbackListResponse,
    FeedbackRequest,
    FeedbackResponse,
    SignalDetailResponse,
    SignalExplainResponse,
    SignalListResponse,
    SignalSummary,
)
from remi.application.portfolio import SignalDigest
from remi.shell.api.dependencies import Ctr
from remi.types.errors import NotFoundError

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])


def _signal_summary(s: Signal) -> SignalSummary:
    return SignalSummary(
        signal_id=s.signal_id,
        signal_type=s.signal_type,
        severity=s.severity.value,
        entity_type=s.entity_type,
        entity_id=s.entity_id,
        entity_name=s.entity_name,
        description=s.description,
        detected_at=s.detected_at.isoformat(),
    )


@router.get("")
async def list_signals(
    c: Ctr,
    manager_id: str | None = None,
    property_id: str | None = None,
    severity: str | None = None,
    signal_type: str | None = None,
) -> SignalListResponse:
    scope: dict[str, str] | None = None
    if manager_id or property_id:
        scope = {}
        if manager_id:
            scope["manager_id"] = manager_id
        if property_id:
            scope["property_id"] = property_id
    signals = await c.signal_store.list_signals(
        scope=scope,
        severity=severity,
        signal_type=signal_type,
    )
    return SignalListResponse(
        count=len(signals),
        signals=[_signal_summary(s) for s in signals],
    )


@router.get("/digest", response_model=SignalDigest)
async def signal_digest(c: Ctr) -> SignalDigest:
    return await c.signal_resolver.digest()


@router.get("/{signal_id}")
async def get_signal(
    signal_id: str,
    c: Ctr,
) -> SignalDetailResponse:
    signal = await c.signal_store.get_signal(signal_id)
    if signal is None:
        raise NotFoundError("Signal", signal_id)
    return SignalDetailResponse(
        **_signal_summary(signal).model_dump(),
    )


@router.get("/{signal_id}/explain")
async def explain_signal(
    signal_id: str,
    c: Ctr,
) -> SignalExplainResponse:
    signal = await c.signal_store.get_signal(signal_id)
    if signal is None:
        raise NotFoundError("Signal", signal_id)
    return SignalExplainResponse(
        **_signal_summary(signal).model_dump(),
        provenance=signal.provenance.value,
        evidence=signal.evidence,
    )


@router.post("/{signal_id}/feedback")
async def record_feedback(
    signal_id: str,
    body: FeedbackRequest,
    c: Ctr,
) -> FeedbackResponse:
    """Record feedback on a signal."""
    import uuid

    from remi.agent.signals import SignalFeedback, SignalOutcome

    signal = await c.signal_store.get_signal(signal_id)
    if signal is None:
        raise NotFoundError("Signal", signal_id)

    outcome = SignalOutcome(body.outcome)
    feedback = SignalFeedback(
        feedback_id=f"fb-{uuid.uuid4().hex[:12]}",
        signal_id=signal_id,
        signal_type=signal.signal_type,
        outcome=outcome,
        actor=body.actor,
        notes=body.notes,
        context=body.context,
    )
    await c.feedback_store.record_feedback(feedback)
    return FeedbackResponse(
        feedback_id=feedback.feedback_id,
        signal_id=signal_id,
        outcome=outcome.value,
    )


@router.get("/{signal_id}/feedback")
async def list_signal_feedback(
    signal_id: str,
    c: Ctr,
) -> FeedbackListResponse:
    """List feedback events for a specific signal."""
    entries = await c.feedback_store.list_feedback(
        signal_id=signal_id,
    )
    return FeedbackListResponse(
        signal_id=signal_id,
        count=len(entries),
        feedback=entries,
    )


@router.get("/feedback/summary/{signal_type}")
async def feedback_summary(
    signal_type: str,
    c: Ctr,
) -> dict[str, Any]:
    """Aggregated feedback stats for a signal type."""
    summary = await c.feedback_store.summarize(signal_type)
    return summary.model_dump(mode="json")
