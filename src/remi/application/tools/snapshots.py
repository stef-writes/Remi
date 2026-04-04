"""snapshot_compare tool — structured metric diffs across time periods.

Layer 3 (Services): computes deltas between two time periods for a
manager or property, returning percentage changes and trend direction
so the LLM doesn't need to write pandas code for basic comparisons.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from remi.application.core.rollups import ManagerSnapshot
from remi.agent.types import ToolArg, ToolDefinition, ToolRegistry
from remi.application.services.monitoring.snapshots.service import SnapshotService


def _avg_snapshots(snapshots: list[ManagerSnapshot]) -> dict[str, float]:
    """Average numeric fields across a list of manager snapshots."""
    if not snapshots:
        return {}
    n = len(snapshots)
    fields = [
        "property_count",
        "total_units",
        "occupied",
        "vacant",
        "occupancy_rate",
        "total_rent",
        "total_market_rent",
        "loss_to_lease",
        "delinquent_count",
        "delinquent_balance",
    ]
    result: dict[str, float] = {}
    for f in fields:
        total = sum(getattr(s, f, 0) for s in snapshots)
        result[f] = round(total / n, 4)
    return result


def _compute_deltas(before: dict[str, float], after: dict[str, float]) -> list[dict[str, Any]]:
    """Compute absolute and percentage deltas, plus trend direction."""
    deltas: list[dict[str, Any]] = []
    for key in after:
        a = before.get(key, 0.0)
        b = after.get(key, 0.0)
        abs_delta = round(b - a, 4)
        pct = round((abs_delta / a) * 100, 2) if a != 0 else None
        if abs_delta > 0:
            trend = "up"
        elif abs_delta < 0:
            trend = "down"
        else:
            trend = "flat"
        deltas.append(
            {
                "metric": key,
                "period_a": round(a, 4),
                "period_b": round(b, 4),
                "delta": abs_delta,
                "pct_change": pct,
                "trend": trend,
            }
        )
    return deltas


def register_snapshot_tools(
    registry: ToolRegistry,
    *,
    snapshot_service: SnapshotService,
) -> None:
    """Register the snapshot_compare tool."""

    async def snapshot_compare(args: dict[str, Any]) -> Any:
        entity_id = args.get("entity_id")
        days_a_start = int(args.get("days_a_start", 90))
        days_a_end = int(args.get("days_a_end", 45))
        days_b_start = int(args.get("days_b_start", 45))
        days_b_end = 0

        now = datetime.now(UTC)
        since_a = now - timedelta(days=days_a_start)
        until_a = now - timedelta(days=days_a_end)
        since_b = now - timedelta(days=days_b_start)

        all_snaps = await snapshot_service.get_history(manager_id=entity_id, since=since_a)

        period_a = [s for s in all_snaps if s.timestamp <= until_a]
        period_b = [s for s in all_snaps if s.timestamp >= since_b]

        if not period_a and not period_b:
            return {
                "error": "No snapshots found for the given entity and periods.",
                "entity_id": entity_id,
                "total_snapshots": len(all_snaps),
            }

        avg_a = _avg_snapshots(period_a)
        avg_b = _avg_snapshots(period_b)
        deltas = _compute_deltas(avg_a, avg_b)

        return {
            "entity_id": entity_id,
            "period_a": {
                "from_days_ago": days_a_start,
                "to_days_ago": days_a_end,
                "snapshots": len(period_a),
            },
            "period_b": {
                "from_days_ago": days_b_start,
                "to_days_ago": days_b_end,
                "snapshots": len(period_b),
            },
            "deltas": deltas,
        }

    registry.register(
        "snapshot_compare",
        snapshot_compare,
        ToolDefinition(
            name="snapshot_compare",
            description=(
                "Compare manager metrics across two time periods. Returns "
                "absolute and percentage deltas for occupancy, rent, "
                "delinquency, and other KPIs. Use to identify trends without "
                "writing code."
            ),
            args=[
                ToolArg(
                    name="entity_id",
                    description="Manager ID to compare (e.g. 'manager:jake-kraus')",
                    required=True,
                ),
                ToolArg(
                    name="days_a_start",
                    description="Start of period A as days ago (default: 90)",
                    type="integer",
                ),
                ToolArg(
                    name="days_a_end",
                    description="End of period A as days ago (default: 45)",
                    type="integer",
                ),
                ToolArg(
                    name="days_b_start",
                    description=(
                        "Start of period B as days ago (default: 45). "
                        "Period B runs from this value to today."
                    ),
                    type="integer",
                ),
            ],
        ),
    )
