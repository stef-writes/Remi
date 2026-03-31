"""Evaluators for temporal trend signals (declining periods, consistent direction)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from remi.knowledge.entailment.base import MakeSignalFn
    from remi.models.properties import PropertyStore
    from remi.models.signals import Signal, SignalDefinition
    from remi.services.snapshots import SnapshotService

_log = structlog.get_logger(__name__)


async def eval_declining_consecutive_periods(
    defn: SignalDefinition,
    ps: PropertyStore,
    snapshots: SnapshotService | None,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Fires when a manager's metric declines over N consecutive snapshot periods."""
    if snapshots is None:
        _log.debug("no_snapshot_service", signal=defn.name)
        return []

    required_periods = defn.rule.periods or 2
    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        history = snapshots.get_history(mgr.id)
        if len(history) < required_periods + 1:
            continue

        recent = sorted(history, key=lambda s: s.timestamp, reverse=True)
        values = [s.occupancy_rate for s in recent[: required_periods + 1]]

        declining_count = sum(1 for i in range(len(values) - 1) if values[i] < values[i + 1])
        if declining_count >= required_periods:
            drop = values[-1] - values[0]
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"Occupancy declined {required_periods} consecutive periods: "
                        f"{values[-1]:.1%} → {values[0]:.1%}"
                    ),
                    evidence={
                        "occupancy_values": [round(v, 4) for v in values],
                        "declining_periods": declining_count,
                        "required_periods": required_periods,
                        "total_drop": round(drop, 4),
                        "timestamps": [
                            s.timestamp.isoformat() for s in recent[: required_periods + 1]
                        ],
                        "manager_id": mgr.id,
                    },
                )
            )
    return signals


async def eval_consistent_direction(
    defn: SignalDefinition,
    ps: PropertyStore,
    snapshots: SnapshotService | None,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Fires when a manager's metrics move consistently in one direction."""
    if snapshots is None:
        _log.debug("no_snapshot_service", signal=defn.name)
        return []

    required_periods = defn.rule.periods or 2
    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        history = snapshots.get_history(mgr.id)
        if len(history) < required_periods + 1:
            continue

        recent = sorted(history, key=lambda s: s.timestamp, reverse=True)
        snaps = recent[: required_periods + 1]
        occ_values = [s.occupancy_rate for s in snaps]
        rent_values = [s.total_rent for s in snaps]

        occ_deltas = [occ_values[i] - occ_values[i + 1] for i in range(len(occ_values) - 1)]
        rent_deltas = [rent_values[i] - rent_values[i + 1] for i in range(len(rent_values) - 1)]

        all_improving = all(d > 0 for d in occ_deltas) or all(d > 0 for d in rent_deltas)
        all_declining = all(d < 0 for d in occ_deltas) or all(d < 0 for d in rent_deltas)

        if not all_improving and not all_declining:
            continue

        direction = "improving" if all_improving else "declining"
        signals.append(
            make_signal(
                defn=defn,
                entity_id=mgr.id,
                entity_name=mgr.name,
                description=(
                    f"Performance {direction} over {required_periods} consecutive "
                    f"periods: occupancy {occ_values[-1]:.1%} → {occ_values[0]:.1%}"
                ),
                evidence={
                    "direction": direction,
                    "occupancy_values": [round(v, 4) for v in occ_values],
                    "rent_values": [round(v, 2) for v in rent_values],
                    "periods": required_periods,
                    "timestamps": [s.timestamp.isoformat() for s in snaps],
                    "manager_id": mgr.id,
                },
            )
        )
    return signals
