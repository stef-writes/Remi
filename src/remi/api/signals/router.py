"""REST endpoints for entailed signals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from remi.api.dependencies import get_feedback_store, get_signal_pipeline, get_signal_store
from remi.api.signals.schemas import (
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
from remi.knowledge.composite import CompositeProducer
from remi.models.signals import FeedbackStore, SignalStore

router = APIRouter(prefix="/signals", tags=["signals"])


def _signal_summary(s) -> SignalSummary:
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
    signals = await ss.list_signals(
        manager_id=manager_id,
        property_id=property_id,
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
        raise HTTPException(404, f"Signal '{signal_id}' not found")
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
        raise HTTPException(404, f"Signal '{signal_id}' not found")
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

    from remi.models.signals import SignalFeedback, SignalOutcome

    signal = await ss.get_signal(signal_id)
    if signal is None:
        raise HTTPException(404, f"Signal '{signal_id}' not found")

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
        feedback=[e.model_dump(mode="json") for e in entries],
    )


@router.get("/feedback/summary/{signal_type}")
async def feedback_summary(
    signal_type: str,
    fs: FeedbackStore = Depends(get_feedback_store),
) -> dict:
    """Aggregated feedback stats for a signal type."""
    summary = await fs.summarize(signal_type)
    return summary.model_dump(mode="json")
