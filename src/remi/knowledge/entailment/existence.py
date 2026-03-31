"""Evaluators for EXISTS and IN_LEGAL_TRACK rule conditions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from remi.knowledge.entailment.base import MakeSignalFn
from remi.models.properties import PropertyStore
from remi.models.signals import Signal, SignalDefinition


async def eval_in_legal_track(
    defn: SignalDefinition,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Fires when an entity matches a set of statuses."""
    statuses = set(defn.rule.statuses or [])
    if not statuses:
        return []

    tenants = await ps.list_tenants()
    signals: list[Signal] = []

    for t in tenants:
        if t.status.value in statuses:
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=t.id,
                    entity_name=t.name,
                    description="Tenant in legal/eviction track",
                    evidence={
                        "tenant_status": t.status.value,
                        "balance_owed": float(t.balance_owed),
                        "tenant_name": t.name,
                    },
                )
            )
    return signals


async def eval_exists(
    defn: SignalDefinition,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Fires when unreported situations exist in the data."""
    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        portfolios = await ps.list_portfolios(manager_id=mgr.id)
        unreported: list[dict[str, Any]] = []

        for pf in portfolios:
            properties = await ps.list_properties(portfolio_id=pf.id)
            for prop in properties:
                tenants = await ps.list_tenants(property_id=prop.id)
                for t in tenants:
                    if t.balance_30_plus > 0 and t.balance_30_plus >= Decimal("500"):
                        unreported.append(
                            {
                                "type": "aging_balance",
                                "tenant_id": t.id,
                                "tenant_name": t.name,
                                "balance_30_plus": float(t.balance_30_plus),
                                "total_owed": float(t.balance_owed),
                                "property_id": prop.id,
                                "property_name": prop.name,
                            }
                        )

                units = await ps.list_units(property_id=prop.id)
                vacant_units = [
                    u
                    for u in units
                    if u.status.value == "vacant"
                    and u.days_vacant is not None
                    and u.days_vacant > 14
                ]
                if len(vacant_units) >= 3:
                    unreported.append(
                        {
                            "type": "high_vacancy_cluster",
                            "property_id": prop.id,
                            "property_name": prop.name,
                            "vacant_count": len(vacant_units),
                            "avg_days_vacant": round(
                                sum(u.days_vacant or 0 for u in vacant_units) / len(vacant_units)
                            ),
                        }
                    )

        if unreported:
            unreported.sort(
                key=lambda r: r.get("balance_30_plus", 0) or r.get("vacant_count", 0),
                reverse=True,
            )
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{len(unreported)} situation(s) visible in data "
                        f"that may not have been surfaced"
                    ),
                    evidence={
                        "unreported_count": len(unreported),
                        "situations": unreported[:20],
                        "manager_id": mgr.id,
                    },
                )
            )
    return signals
