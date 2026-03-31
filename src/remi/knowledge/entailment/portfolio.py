"""Evaluators for concentration risk and below-percentile portfolio signals."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from remi.knowledge.entailment.base import MakeSignalFn
from remi.models.properties import PropertyStore
from remi.models.signals import DomainOntology, Signal, SignalDefinition


async def eval_manager_concentration_risk(
    defn: SignalDefinition,
    domain: DomainOntology,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Fires when a single property dominates a manager's revenue stream."""
    threshold_key = defn.rule.threshold_key or "concentration_risk_pct"
    threshold = domain.threshold(threshold_key, 0.40)
    managers = await ps.list_managers()
    signals: list[Signal] = []

    for mgr in managers:
        portfolios = await ps.list_portfolios(manager_id=mgr.id)
        property_revenue: list[tuple[str, str, float]] = []
        total_revenue = Decimal("0")

        for pf in portfolios:
            properties = await ps.list_properties(portfolio_id=pf.id)
            for prop in properties:
                leases = await ps.list_leases(property_id=prop.id)
                prop_rent = sum(
                    (ls.monthly_rent for ls in leases if ls.status.value == "active"),
                    Decimal("0"),
                )
                total_revenue += prop_rent
                property_revenue.append((prop.id, prop.name, float(prop_rent)))

        if total_revenue <= 0 or len(property_revenue) < 2:
            continue

        total_f = float(total_revenue)
        concentrated = [
            (pid, pname, rev, rev / total_f)
            for pid, pname, rev in property_revenue
            if rev / total_f >= threshold
        ]

        if concentrated:
            concentrated.sort(key=lambda x: x[3], reverse=True)
            top = concentrated[0]
            signals.append(
                make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{top[1]} represents {top[3]:.0%} of portfolio revenue "
                        f"(threshold: {threshold:.0%})"
                    ),
                    evidence={
                        "concentrated_properties": [
                            {
                                "property_id": pid,
                                "property_name": pname,
                                "monthly_revenue": round(rev, 2),
                                "pct_of_total": round(pct, 4),
                            }
                            for pid, pname, rev, pct in concentrated
                        ],
                        "total_portfolio_revenue": round(total_f, 2),
                        "threshold_pct": threshold,
                        "property_count": len(property_revenue),
                        "manager_id": mgr.id,
                    },
                )
            )
    return signals


async def eval_below_percentile(
    defn: SignalDefinition,
    domain: DomainOntology,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Fires when a manager's composite metric is below the Nth percentile of peers."""
    percentile = defn.rule.percentile or 25
    managers = await ps.list_managers()
    if len(managers) < 2:
        return []

    scores: list[tuple[Any, float]] = []
    for mgr in managers:
        portfolios = await ps.list_portfolios(manager_id=mgr.id)
        total_units = 0
        occupied = 0
        total_rent = Decimal("0")
        total_owed = Decimal("0")

        for pf in portfolios:
            properties = await ps.list_properties(portfolio_id=pf.id)
            for prop in properties:
                units = await ps.list_units(property_id=prop.id)
                for u in units:
                    total_units += 1
                    if u.status.value == "occupied":
                        occupied += 1
                    total_rent += u.current_rent
                tenants = await ps.list_tenants(property_id=prop.id)
                for t in tenants:
                    total_owed += t.balance_owed

        occ_rate = occupied / total_units if total_units else 0.0
        delinq_penalty = float(total_owed / total_rent) if total_rent > 0 else 0.0
        composite = occ_rate - delinq_penalty
        scores.append((mgr, composite))

    scores.sort(key=lambda x: x[1])
    cutoff_idx = max(1, len(scores) * percentile // 100)
    cutoff_value = scores[cutoff_idx - 1][1] if scores else 0.0

    signals: list[Signal] = []
    for mgr, score in scores[:cutoff_idx]:
        rank = next(i + 1 for i, (m, _) in enumerate(scores) if m.id == mgr.id)
        signals.append(
            make_signal(
                defn=defn,
                entity_id=mgr.id,
                entity_name=mgr.name,
                description=(
                    f"Composite score {score:.2f} is in bottom {percentile}th "
                    f"percentile (rank {rank}/{len(scores)})"
                ),
                evidence={
                    "composite_score": round(score, 4),
                    "rank": rank,
                    "total_managers": len(scores),
                    "percentile_cutoff": percentile,
                    "cutoff_value": round(cutoff_value, 4),
                    "manager_id": mgr.id,
                },
            )
        )
    return signals
