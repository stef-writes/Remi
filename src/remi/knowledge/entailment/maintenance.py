"""Evaluators for maintenance backlog and aging-past-threshold."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from remi.knowledge.entailment.base import MakeSignalFn
from remi.models.properties import PropertyStore
from remi.models.signals import DomainRulebook, Signal, SignalDefinition


async def eval_manager_maintenance_backlog(
    defn: SignalDefinition,
    domain: DomainRulebook,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    threshold_key = defn.rule.threshold_key or "maintenance_backlog_days"
    threshold_days = int(domain.threshold(threshold_key, 30))
    now = datetime.now(UTC)
    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        portfolios = await ps.list_portfolios(manager_id=mgr.id)
        aging_requests: list[dict[str, Any]] = []

        for pf in portfolios:
            properties = await ps.list_properties(portfolio_id=pf.id)
            for prop in properties:
                requests = await ps.list_maintenance_requests(property_id=prop.id)
                for req in requests:
                    if req.status.value in ("open", "in_progress"):
                        age_days = (now - req.created_at).days
                        if age_days > threshold_days:
                            aging_requests.append(
                                {
                                    "request_id": req.id,
                                    "title": req.title,
                                    "age_days": age_days,
                                    "priority": req.priority.value,
                                    "property_id": prop.id,
                                    "property_name": prop.name,
                                    "unit_id": req.unit_id,
                                }
                            )

        if aging_requests:
            aging_requests.sort(key=lambda r: r["age_days"], reverse=True)
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{len(aging_requests)} work orders open longer than {threshold_days} days"
                    ),
                    evidence={
                        "aging_count": len(aging_requests),
                        "threshold_days": threshold_days,
                        "aging_requests": aging_requests[:20],
                        "manager_id": mgr.id,
                    },
                )
            )
    return signals
