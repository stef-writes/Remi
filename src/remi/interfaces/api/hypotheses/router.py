"""REST endpoints for the hypothesis lifecycle.

Hypotheses are candidate TBox entries discovered by PatternDetector
(induction). These endpoints let the director agent or a human operator
review, confirm, reject, and graduate them into live domain knowledge.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from remi.domain.signals.hypothesis import HypothesisStatus
from remi.interfaces.api.dependencies import get_container

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(prefix="/hypotheses", tags=["hypotheses"])


class ReviewRequest(BaseModel):
    reviewed_by: str = ""
    review_notes: str = ""


@router.get("")
async def list_hypotheses(
    kind: str | None = None,
    status: str | None = None,
    min_confidence: float | None = None,
    limit: int = 50,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """List hypotheses with optional filters."""
    results = await container.hypothesis_store.list_hypotheses(
        kind=kind,
        status=status,
        min_confidence=min_confidence,
        limit=limit,
    )
    return {
        "count": len(results),
        "hypotheses": [h.model_dump(mode="json") for h in results],
    }


@router.get("/{hypothesis_id}")
async def get_hypothesis(
    hypothesis_id: str,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Get a single hypothesis by ID."""
    hyp = await container.hypothesis_store.get(hypothesis_id)
    if hyp is None:
        raise HTTPException(404, "Hypothesis not found")
    return hyp.model_dump(mode="json")


@router.post("/{hypothesis_id}/confirm")
async def confirm_hypothesis(
    hypothesis_id: str,
    body: ReviewRequest | None = None,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Confirm a hypothesis — marks it ready for graduation."""
    review = body or ReviewRequest()
    updated = await container.hypothesis_store.update_status(
        hypothesis_id,
        HypothesisStatus.CONFIRMED,
        reviewed_by=review.reviewed_by,
        review_notes=review.review_notes,
    )
    if updated is None:
        raise HTTPException(404, "Hypothesis not found")
    return {"status": "confirmed", "hypothesis": updated.model_dump(mode="json")}


@router.post("/{hypothesis_id}/reject")
async def reject_hypothesis(
    hypothesis_id: str,
    body: ReviewRequest | None = None,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Reject a hypothesis — it will not be graduated."""
    review = body or ReviewRequest()
    updated = await container.hypothesis_store.update_status(
        hypothesis_id,
        HypothesisStatus.REJECTED,
        reviewed_by=review.reviewed_by,
        review_notes=review.review_notes,
    )
    if updated is None:
        raise HTTPException(404, "Hypothesis not found")
    return {"status": "rejected", "hypothesis": updated.model_dump(mode="json")}


@router.post("/{hypothesis_id}/graduate")
async def graduate_hypothesis(
    hypothesis_id: str,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Graduate a confirmed hypothesis into the live TBox."""
    result = await container.hypothesis_graduator.graduate(hypothesis_id)
    if not result.graduated:
        raise HTTPException(
            400,
            f"Could not graduate: {result.reason}",
        )
    return {
        "graduated": True,
        "hypothesis_id": result.hypothesis_id,
        "tbox_entries_created": result.tbox_entries_created,
    }


@router.post("/detect")
async def run_pattern_detection(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Run the pattern detector to discover new hypotheses."""
    result = await container.pattern_detector.run()
    return {
        "proposed": result.proposed,
        "errors": result.errors,
        "types_scanned": result.types_scanned,
        "hypotheses": [h.model_dump(mode="json") for h in result.hypotheses],
    }


@router.post("/graduate-all")
async def graduate_all_confirmed(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Graduate all confirmed hypotheses into the live TBox."""
    results = await container.hypothesis_graduator.graduate_all_confirmed()
    graduated = [r for r in results if r.graduated]
    failed = [r for r in results if not r.graduated]
    return {
        "graduated_count": len(graduated),
        "failed_count": len(failed),
        "results": [
            {
                "hypothesis_id": r.hypothesis_id,
                "graduated": r.graduated,
                "reason": r.reason,
                "entries": r.tbox_entries_created,
            }
            for r in results
        ],
    }
