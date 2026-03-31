"""REST endpoints for entailed signals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

from remi.interfaces.api.dependencies import get_container

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def list_signals(
    manager_id: str | None = None,
    property_id: str | None = None,
    severity: str | None = None,
    signal_type: str | None = None,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    signals = await container.signal_store.list_signals(
        manager_id=manager_id,
        property_id=property_id,
        severity=severity,
        signal_type=signal_type,
    )
    return {
        "count": len(signals),
        "signals": [
            {
                "signal_id": s.signal_id,
                "signal_type": s.signal_type,
                "severity": s.severity.value,
                "entity_type": s.entity_type,
                "entity_id": s.entity_id,
                "entity_name": s.entity_name,
                "description": s.description,
                "detected_at": s.detected_at.isoformat(),
            }
            for s in signals
        ],
    }


@router.get("/{signal_id}")
async def get_signal(
    signal_id: str,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    signal = await container.signal_store.get_signal(signal_id)
    if signal is None:
        raise HTTPException(404, f"Signal '{signal_id}' not found")
    return {
        "signal_id": signal.signal_id,
        "signal_type": signal.signal_type,
        "severity": signal.severity.value,
        "entity_type": signal.entity_type,
        "entity_id": signal.entity_id,
        "entity_name": signal.entity_name,
        "description": signal.description,
        "detected_at": signal.detected_at.isoformat(),
    }


@router.get("/{signal_id}/explain")
async def explain_signal(
    signal_id: str,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    signal = await container.signal_store.get_signal(signal_id)
    if signal is None:
        raise HTTPException(404, f"Signal '{signal_id}' not found")
    return {
        "signal_id": signal.signal_id,
        "signal_type": signal.signal_type,
        "severity": signal.severity.value,
        "entity_type": signal.entity_type,
        "entity_id": signal.entity_id,
        "entity_name": signal.entity_name,
        "description": signal.description,
        "provenance": signal.provenance.value,
        "detected_at": signal.detected_at.isoformat(),
        "evidence": signal.evidence,
    }


@router.post("/infer")
async def run_entailment(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    result = await container.signal_pipeline.run_all()
    per_source = {
        name: {"produced": pr.produced, "errors": pr.errors}
        for name, pr in result.per_source.items()
    }
    return {
        "produced": result.produced,
        "signal_count": len(result.signals),
        "sources": per_source,
        "trace_id": result.trace_id,
    }


# -- Feedback -----------------------------------------------------------------


@router.post("/{signal_id}/feedback")
async def record_feedback(
    signal_id: str,
    body: dict[str, Any],
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Record feedback on a signal (acknowledged, dismissed, acted_on, etc.)."""
    import uuid

    from remi.domain.signals.feedback import SignalFeedback, SignalOutcome

    signal = await container.signal_store.get_signal(signal_id)
    if signal is None:
        raise HTTPException(404, f"Signal '{signal_id}' not found")

    outcome = SignalOutcome(body.get("outcome", "acknowledged"))
    feedback = SignalFeedback(
        feedback_id=f"fb-{uuid.uuid4().hex[:12]}",
        signal_id=signal_id,
        signal_type=signal.signal_type,
        outcome=outcome,
        actor=body.get("actor", ""),
        notes=body.get("notes", ""),
        context=body.get("context", {}),
    )
    await container.feedback_store.record_feedback(feedback)
    return {
        "ok": True,
        "feedback_id": feedback.feedback_id,
        "signal_id": signal_id,
        "outcome": outcome.value,
    }


@router.get("/{signal_id}/feedback")
async def list_signal_feedback(
    signal_id: str,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """List feedback events for a specific signal."""
    entries = await container.feedback_store.list_feedback(signal_id=signal_id)
    return {
        "signal_id": signal_id,
        "count": len(entries),
        "feedback": [e.model_dump(mode="json") for e in entries],
    }


@router.get("/feedback/summary/{signal_type}")
async def feedback_summary(
    signal_type: str,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Aggregated feedback stats for a signal type."""
    summary = await container.feedback_store.summarize(signal_type)
    return summary.model_dump(mode="json")
