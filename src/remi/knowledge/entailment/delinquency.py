"""Evaluator for EXCEEDS_THRESHOLD on manager delinquency rate."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from remi.knowledge.entailment.base import MakeSignalFn
    from remi.models.properties import PropertyStore
    from remi.models.signals import DomainOntology, Signal, SignalDefinition


async def eval_manager_delinquency(
    defn: SignalDefinition,
    domain: DomainOntology,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    threshold_key = defn.rule.threshold_key or "delinquency_critical_pct"
    critical_pct = domain.threshold(threshold_key, 0.08)
    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        portfolios = await ps.list_portfolios(manager_id=mgr.id)
        total_rent = Decimal("0")
        total_owed = Decimal("0")
        delinquent_tenants: list[dict[str, Any]] = []

        for pf in portfolios:
            properties = await ps.list_properties(portfolio_id=pf.id)
            for prop in properties:
                tenants = await ps.list_tenants(property_id=prop.id)
                leases = await ps.list_leases(property_id=prop.id)
                active_rents = {
                    lease.tenant_id: lease.monthly_rent
                    for lease in leases
                    if lease.status.value == "active"
                }
                for t in tenants:
                    rent = active_rents.get(t.id, Decimal("0"))
                    total_rent += rent
                    if t.balance_owed > 0:
                        total_owed += t.balance_owed
                        delinquent_tenants.append(
                            {
                                "tenant_id": t.id,
                                "name": t.name,
                                "balance_owed": float(t.balance_owed),
                                "balance_30_plus": float(t.balance_30_plus),
                                "property_id": prop.id,
                                "property_name": prop.name,
                            }
                        )

        if total_rent <= 0:
            continue

        rate = float(total_owed / total_rent)
        if rate >= critical_pct:
            delinquent_tenants.sort(key=lambda d: d["balance_owed"], reverse=True)
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"Delinquency rate {rate:.1%} exceeds threshold {critical_pct:.1%}"
                    ),
                    evidence={
                        "delinquency_rate": round(rate, 4),
                        "total_owed": float(total_owed),
                        "gross_rent_roll": float(total_rent),
                        "threshold_pct": critical_pct,
                        "delinquent_count": len(delinquent_tenants),
                        "delinquent_tenants": delinquent_tenants[:20],
                        "manager_id": mgr.id,
                    },
                )
            )
    return signals
