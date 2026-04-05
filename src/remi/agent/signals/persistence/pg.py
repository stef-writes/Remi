"""Postgres-backed SignalStore and FeedbackStore."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from remi.agent.db.tables import SignalFeedbackRow, SignalRow
from remi.agent.graph.types import KnowledgeProvenance as Provenance
from remi.agent.signals.enums import Severity, SignalOutcome
from remi.agent.signals.feedback import SignalFeedback, SignalFeedbackSummary
from remi.agent.signals.persistence.stores import FeedbackStore, SignalStore
from remi.agent.signals.signal import Signal

_log = structlog.get_logger(__name__)

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


def _signal_to_row(signal: Signal) -> SignalRow:
    return SignalRow(
        signal_id=signal.signal_id,
        signal_type=signal.signal_type,
        severity=signal.severity.value,
        entity_type=signal.entity_type,
        entity_id=signal.entity_id,
        entity_name=signal.entity_name,
        description=signal.description,
        evidence=signal.evidence,
        detected_at=signal.detected_at,
        provenance=signal.provenance.value,
    )


def _row_to_signal(row: SignalRow) -> Signal:
    return Signal(
        signal_id=row.signal_id,
        signal_type=row.signal_type,
        severity=Severity(row.severity),
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        entity_name=row.entity_name,
        description=row.description,
        evidence=row.evidence or {},
        detected_at=row.detected_at,
        provenance=Provenance(row.provenance),
    )


def _feedback_to_row(fb: SignalFeedback) -> SignalFeedbackRow:
    return SignalFeedbackRow(
        feedback_id=fb.feedback_id,
        signal_id=fb.signal_id,
        signal_type=fb.signal_type,
        outcome=fb.outcome.value,
        actor=fb.actor,
        notes=fb.notes,
        context=fb.context,
        recorded_at=fb.recorded_at,
    )


def _row_to_feedback(row: SignalFeedbackRow) -> SignalFeedback:
    return SignalFeedback(
        feedback_id=row.feedback_id,
        signal_id=row.signal_id,
        signal_type=row.signal_type,
        outcome=SignalOutcome(row.outcome),
        actor=row.actor,
        notes=row.notes,
        context=row.context or {},
        recorded_at=row.recorded_at,
    )


class PostgresSignalStore(SignalStore):
    """Postgres-backed signal store."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def put_signal(self, signal: Signal) -> None:
        async with self._sf() as session:
            existing = await session.get(SignalRow, signal.signal_id)
            if existing is not None:
                existing.signal_type = signal.signal_type
                existing.severity = signal.severity.value
                existing.entity_type = signal.entity_type
                existing.entity_id = signal.entity_id
                existing.entity_name = signal.entity_name
                existing.description = signal.description
                existing.evidence = signal.evidence
                existing.detected_at = signal.detected_at
                existing.provenance = signal.provenance.value
                session.add(existing)
            else:
                session.add(_signal_to_row(signal))
            await session.commit()

    async def get_signal(self, signal_id: str) -> Signal | None:
        async with self._sf() as session:
            row = await session.get(SignalRow, signal_id)
            return _row_to_signal(row) if row else None

    async def list_signals(
        self,
        *,
        scope: dict[str, str] | None = None,
        severity: str | None = None,
        signal_type: str | None = None,
    ) -> list[Signal]:
        async with self._sf() as session:
            stmt = select(SignalRow)
            if severity is not None:
                stmt = stmt.where(col(SignalRow.severity) == severity)
            if signal_type is not None:
                stmt = stmt.where(col(SignalRow.signal_type) == signal_type)
            result = await session.exec(stmt)
            signals = [_row_to_signal(r) for r in result.all()]

        if scope:
            signals = [s for s in signals if _matches_scope(s, scope)]

        signals.sort(key=lambda s: (_SEVERITY_ORDER.get(s.severity, 9), s.signal_type))
        return signals

    async def retire_signal(self, signal_id: str) -> None:
        async with self._sf() as session:
            row = await session.get(SignalRow, signal_id)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def clear_all(self) -> None:
        async with self._sf() as session:
            stmt = select(SignalRow)
            result = await session.exec(stmt)
            for row in result.all():
                await session.delete(row)
            await session.commit()


class PostgresFeedbackStore(FeedbackStore):
    """Postgres-backed feedback store."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def record_feedback(self, feedback: SignalFeedback) -> None:
        async with self._sf() as session:
            existing = await session.get(SignalFeedbackRow, feedback.feedback_id)
            if existing is not None:
                existing.outcome = feedback.outcome.value
                existing.notes = feedback.notes
                existing.context = feedback.context
                session.add(existing)
            else:
                session.add(_feedback_to_row(feedback))
            await session.commit()

    async def get_feedback(self, feedback_id: str) -> SignalFeedback | None:
        async with self._sf() as session:
            row = await session.get(SignalFeedbackRow, feedback_id)
            return _row_to_feedback(row) if row else None

    async def list_feedback(
        self,
        *,
        signal_id: str | None = None,
        signal_type: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[SignalFeedback]:
        async with self._sf() as session:
            stmt = select(SignalFeedbackRow)
            if signal_id:
                stmt = stmt.where(col(SignalFeedbackRow.signal_id) == signal_id)
            if signal_type:
                stmt = stmt.where(col(SignalFeedbackRow.signal_type) == signal_type)
            if outcome:
                stmt = stmt.where(col(SignalFeedbackRow.outcome) == outcome)
            stmt = stmt.order_by(col(SignalFeedbackRow.recorded_at).desc()).limit(limit)
            result = await session.exec(stmt)
            return [_row_to_feedback(r) for r in result.all()]

    async def summarize(self, signal_type: str) -> SignalFeedbackSummary:
        async with self._sf() as session:
            stmt = select(SignalFeedbackRow).where(
                col(SignalFeedbackRow.signal_type) == signal_type,
            )
            result = await session.exec(stmt)
            rows = result.all()

        total = len(rows)
        if total == 0:
            return SignalFeedbackSummary(signal_type=signal_type)

        counts: dict[str, int] = {}
        for row in rows:
            counts[row.outcome] = counts.get(row.outcome, 0) + 1

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


def _matches_scope(signal: Signal, scope: dict[str, str]) -> bool:
    for key, value in scope.items():
        if signal.entity_id == value:
            continue
        if signal.evidence.get(key) == value:
            continue
        return False
    return True
