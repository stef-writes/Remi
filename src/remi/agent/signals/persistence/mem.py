"""In-memory stores for signals and feedback."""

from __future__ import annotations

from remi.agent.signals.enums import Severity, SignalOutcome
from remi.agent.signals.feedback import SignalFeedback, SignalFeedbackSummary
from remi.agent.signals.persistence.stores import FeedbackStore, SignalStore
from remi.agent.signals.signal import Signal

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


def _matches_scope(signal: Signal, scope: dict[str, str]) -> bool:
    """Check whether a signal matches all scope key-value pairs.

    A scope entry matches if the value equals entity_id or is present
    in evidence under the same key.
    """
    for key, value in scope.items():
        if signal.entity_id == value:
            continue
        if signal.evidence.get(key) == value:
            continue
        return False
    return True


class InMemorySignalStore(SignalStore):
    def __init__(self) -> None:
        self._signals: dict[str, Signal] = {}

    def dump_state(self) -> list[dict[str, object]]:
        return [s.model_dump(mode="json") for s in self._signals.values()]

    def load_state(self, data: list[dict[str, object]]) -> None:
        self._signals.clear()
        for raw in data:
            sig = Signal.model_validate(raw)
            self._signals[sig.signal_id] = sig

    async def put_signal(self, signal: Signal) -> None:
        self._signals[signal.signal_id] = signal

    async def get_signal(self, signal_id: str) -> Signal | None:
        return self._signals.get(signal_id)

    async def list_signals(
        self,
        *,
        scope: dict[str, str] | None = None,
        severity: str | None = None,
        signal_type: str | None = None,
    ) -> list[Signal]:
        results = list(self._signals.values())

        if scope:
            results = [s for s in results if _matches_scope(s, scope)]
        if severity is not None:
            results = [s for s in results if s.severity.value == severity]
        if signal_type is not None:
            results = [s for s in results if s.signal_type == signal_type]

        results.sort(key=lambda s: (_SEVERITY_ORDER.get(s.severity, 9), s.signal_type))
        return results

    async def retire_signal(self, signal_id: str) -> None:
        self._signals.pop(signal_id, None)

    async def clear_all(self) -> None:
        self._signals.clear()


class InMemoryFeedbackStore(FeedbackStore):
    """Simple dict-backed feedback store for development and testing."""

    def __init__(self) -> None:
        self._entries: dict[str, SignalFeedback] = {}

    def dump_state(self) -> list[dict[str, object]]:
        return [f.model_dump(mode="json") for f in self._entries.values()]

    def load_state(self, data: list[dict[str, object]]) -> None:
        self._entries.clear()
        for raw in data:
            fb = SignalFeedback.model_validate(raw)
            self._entries[fb.feedback_id] = fb

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
        relevant = [fb for fb in self._entries.values() if fb.signal_type == signal_type]
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
