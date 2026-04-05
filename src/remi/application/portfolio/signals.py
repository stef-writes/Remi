"""Signals — digest and entity-grouped views."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from remi.agent.signals import Signal, SignalStore


class SignalEntityGroup(BaseModel, frozen=True):
    entity_id: str
    entity_type: str
    entity_name: str
    worst_severity: str
    signal_count: int
    severity_counts: dict[str, int]
    signals: list[SignalSummaryItem]


class SignalSummaryItem(BaseModel, frozen=True):
    signal_id: str
    signal_type: str
    severity: str
    entity_type: str
    entity_id: str
    entity_name: str
    description: str
    detected_at: str


class SignalDigest(BaseModel, frozen=True):
    total_signals: int
    total_entities: int
    severity_counts: dict[str, int]
    entities: list[SignalEntityGroup]


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class SignalResolver:
    """Read-side resolver for signal aggregation views."""

    def __init__(self, signal_store: SignalStore) -> None:
        self._ss = signal_store

    async def digest(self) -> SignalDigest:
        """Grouped signal briefing — entities sorted by worst severity."""
        all_signals = await self._ss.list_signals()

        by_entity: dict[str, list[Signal]] = defaultdict(list)
        for s in all_signals:
            by_entity[s.entity_id].append(s)

        groups: list[SignalEntityGroup] = []
        for entity_id, sigs in by_entity.items():
            sigs.sort(key=lambda s: _SEVERITY_RANK.get(s.severity.value, 99))
            worst = sigs[0]

            severity_counts: dict[str, int] = defaultdict(int)
            for s in sigs:
                severity_counts[s.severity.value] += 1

            items = [
                SignalSummaryItem(
                    signal_id=s.signal_id,
                    signal_type=s.signal_type,
                    severity=s.severity.value,
                    entity_type=s.entity_type,
                    entity_id=s.entity_id,
                    entity_name=s.entity_name,
                    description=s.description,
                    detected_at=s.detected_at.isoformat(),
                )
                for s in sigs
            ]

            groups.append(SignalEntityGroup(
                entity_id=entity_id,
                entity_type=worst.entity_type,
                entity_name=worst.entity_name,
                worst_severity=worst.severity.value,
                signal_count=len(sigs),
                severity_counts=dict(severity_counts),
                signals=items,
            ))

        groups.sort(key=lambda g: _SEVERITY_RANK.get(g.worst_severity, 99))

        total_by_severity: dict[str, int] = defaultdict(int)
        for s in all_signals:
            total_by_severity[s.severity.value] += 1

        return SignalDigest(
            total_signals=len(all_signals),
            total_entities=len(groups),
            severity_counts=dict(total_by_severity),
            entities=groups,
        )
