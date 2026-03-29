"""In-memory implementation of HypothesisStore."""

from __future__ import annotations

from datetime import UTC, datetime

from remi.domain.signals.hypothesis import (
    Hypothesis,
    HypothesisStatus,
    HypothesisStore,
)


class InMemoryHypothesisStore(HypothesisStore):
    """Dict-backed hypothesis store for development and testing."""

    def __init__(self) -> None:
        self._entries: dict[str, Hypothesis] = {}

    async def put(self, hypothesis: Hypothesis) -> None:
        self._entries[hypothesis.hypothesis_id] = hypothesis

    async def get(self, hypothesis_id: str) -> Hypothesis | None:
        return self._entries.get(hypothesis_id)

    async def list_hypotheses(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        min_confidence: float | None = None,
        limit: int = 50,
    ) -> list[Hypothesis]:
        results: list[Hypothesis] = []
        for h in self._entries.values():
            if kind and h.kind.value != kind:
                continue
            if status and h.status.value != status:
                continue
            if min_confidence is not None and h.confidence < min_confidence:
                continue
            results.append(h)
            if len(results) >= limit:
                break
        return sorted(results, key=lambda h: h.proposed_at, reverse=True)

    async def update_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        *,
        reviewed_by: str = "",
        review_notes: str = "",
    ) -> Hypothesis | None:
        existing = self._entries.get(hypothesis_id)
        if existing is None:
            return None

        updated = Hypothesis(
            **{
                **existing.model_dump(),
                "status": status,
                "reviewed_by": reviewed_by,
                "review_notes": review_notes,
                "reviewed_at": datetime.now(UTC),
            }
        )
        self._entries[hypothesis_id] = updated
        return updated
