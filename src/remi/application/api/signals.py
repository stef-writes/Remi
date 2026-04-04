"""REST endpoints for entailed signals."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from remi.agent.signals import FeedbackStore, SignalStore
from remi.agent.signals.producers.composite import CompositeProducer
from remi.agent.signals.signal import Signal
from remi.application.api.signal_schemas import (
    EntailmentResponse,
    FeedbackListResponse,
    FeedbackRequest,
    FeedbackResponse,
    SignalDetailResponse,
    SignalExplainResponse,
    SignalListResponse,
    SignalSummary,
    SourceResult,
)
from remi.application.api.dependencies import (
    get_feedback_store,
    get_signal_pipeline,
    get_signal_store,
)
from remi.types.errors import NotFoundError

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
    manager_id: str | None = None,
    property_id: str | None = None,
    severity: str | None = None,
    signal_type: str | None = None,
    ss: SignalStore = Depends(get_signal_store),
) -> SignalListResponse:
    scope: dict[str, str] | None = None
    if manager_id or property_id:
        scope = {}
        if manager_id:
            scope["manager_id"] = manager_id
        if property_id:
            scope["property_id"] = property_id
    signals = await ss.list_signals(
        scope=scope,
        severity=severity,
        signal_type=signal_type,
    )
    return SignalListResponse(
        count=len(signals),
        signals=[_signal_summary(s) for s in signals],
    )


@router.get("/{signal_id}")
async def get_signal(
    signal_id: str,
    ss: SignalStore = Depends(get_signal_store),
) -> SignalDetailResponse:
    signal = await ss.get_signal(signal_id)
    if signal is None:
        raise NotFoundError("Signal", signal_id)
    return SignalDetailResponse(
        **_signal_summary(signal).model_dump(),
    )


@router.get("/{signal_id}/explain")
async def explain_signal(
    signal_id: str,
    ss: SignalStore = Depends(get_signal_store),
) -> SignalExplainResponse:
    signal = await ss.get_signal(signal_id)
    if signal is None:
        raise NotFoundError("Signal", signal_id)
    return SignalExplainResponse(
        **_signal_summary(signal).model_dump(),
        provenance=signal.provenance.value,
        evidence=signal.evidence,
    )


@router.post("/infer")
async def run_entailment(
    pipeline: CompositeProducer = Depends(get_signal_pipeline),
) -> EntailmentResponse:
    result = await pipeline.run_all()
    sources = {
        name: SourceResult(
            produced=pr.produced,
            errors=pr.errors,
        )
        for name, pr in result.per_source.items()
    }
    return EntailmentResponse(
        produced=result.produced,
        signal_count=len(result.signals),
        sources=sources,
        trace_id=result.trace_id,
    )


@router.post("/{signal_id}/feedback")
async def record_feedback(
    signal_id: str,
    body: FeedbackRequest,
    ss: SignalStore = Depends(get_signal_store),
    fs: FeedbackStore = Depends(get_feedback_store),
) -> FeedbackResponse:
    """Record feedback on a signal."""
    import uuid

    from remi.agent.signals import SignalFeedback, SignalOutcome

    signal = await ss.get_signal(signal_id)
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
    await fs.record_feedback(feedback)
    return FeedbackResponse(
        feedback_id=feedback.feedback_id,
        signal_id=signal_id,
        outcome=outcome.value,
    )


@router.get("/{signal_id}/feedback")
async def list_signal_feedback(
    signal_id: str,
    fs: FeedbackStore = Depends(get_feedback_store),
) -> FeedbackListResponse:
    """List feedback events for a specific signal."""
    entries = await fs.list_feedback(
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
    fs: FeedbackStore = Depends(get_feedback_store),
) -> dict[str, Any]:
    """Aggregated feedback stats for a signal type."""
    summary = await fs.summarize(signal_type)
    return summary.model_dump(mode="json")
