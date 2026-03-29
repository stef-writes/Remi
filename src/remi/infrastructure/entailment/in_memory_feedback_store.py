"""In-memory implementation of FeedbackStore."""

from __future__ import annotations

from remi.domain.signals.feedback import (
    FeedbackStore,
    SignalFeedback,
    SignalFeedbackSummary,
    SignalOutcome,
)


class InMemoryFeedbackStore(FeedbackStore):
    """Simple dict-backed feedback store for development and testing."""

    def __init__(self) -> None:
        self._entries: dict[str, SignalFeedback] = {}

    async def record_feedback(self, feedback: SignalFeedback) -> None:
        self._entries[feedback.feedback_id] = feedback

    async def get_feedback(self, feedback_id: str) -> SignalFeedback | None:
        return self._entries.get(feedback_id)

    async def list_feedback(
        self,
        *,
        signal_id: str | None = None,
        signal_type: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[SignalFeedback]:
        results: list[SignalFeedback] = []
        for fb in self._entries.values():
            if signal_id and fb.signal_id != signal_id:
                continue
            if signal_type and fb.signal_type != signal_type:
                continue
            if outcome and fb.outcome.value != outcome:
                continue
            results.append(fb)
            if len(results) >= limit:
                break
        return sorted(results, key=lambda f: f.recorded_at, reverse=True)

    async def summarize(self, signal_type: str) -> SignalFeedbackSummary:
        relevant = [
            fb for fb in self._entries.values()
            if fb.signal_type == signal_type
        ]
        total = len(relevant)
        if total == 0:
            return SignalFeedbackSummary(signal_type=signal_type)

        counts: dict[str, int] = {}
        for fb in relevant:
            key = fb.outcome.value
            counts[key] = counts.get(key, 0) + 1

        acted = counts.get(SignalOutcome.ACTED_ON.value, 0)
        escalated = counts.get(SignalOutcome.ESCALATED.value, 0)
        dismissed = counts.get(SignalOutcome.DISMISSED.value, 0)
        false_pos = counts.get(SignalOutcome.FALSE_POSITIVE.value, 0)

        act_rate = (acted + escalated) / total if total else 0.0
        dismiss_rate = (dismissed + false_pos) / total if total else 0.0

        return SignalFeedbackSummary(
            signal_type=signal_type,
            total_feedback=total,
            outcome_counts=counts,
            act_rate=round(act_rate, 4),
            dismiss_rate=round(dismiss_rate, 4),
        )
