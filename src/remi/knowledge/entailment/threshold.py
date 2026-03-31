"""Evaluators for EXCEEDS_THRESHOLD and unit-level threshold checks."""

from __future__ import annotations

from typing import Any

from remi.knowledge.entailment.base import MakeSignalFn
from remi.models.properties import PropertyStore
from remi.models.signals import DomainRulebook, Signal, SignalDefinition


async def eval_unit_threshold(
    defn: SignalDefinition,
    domain: DomainRulebook,
    ps: PropertyStore,
    make_signal: MakeSignalFn,
) -> list[Signal]:
    """Evaluate a threshold rule against units."""
    rule = defn.rule
    threshold_key = rule.threshold_key or ""
    threshold = domain.threshold(threshold_key, 0)
    units = await ps.list_units()
    signals: list[Signal] = []

    for unit in units:
        value = _read_unit_metric(unit, rule.metric)
        if value is None or value <= threshold:
            continue

        prop = await ps.get_property(unit.property_id)
        prop_name = prop.name if prop else unit.property_id
        manager_id = await _resolve_manager_id(unit.property_id, ps)

        if rule.metric == "days_vacant":
            desc = f"Unit vacant for {value} days (threshold: {int(threshold)})"
            evidence: dict[str, Any] = {
                "days_vacant": value,
                "threshold": int(threshold),
                "property_id": unit.property_id,
                "property_name": prop_name,
                "unit_number": unit.unit_number,
                "market_rent": float(unit.market_rent),
                "manager_id": manager_id,
            }
        elif rule.metric == "rent_gap_pct":
            if unit.market_rent <= 0 or unit.current_rent <= 0:
                continue
            gap = float((unit.market_rent - unit.current_rent) / unit.market_rent)
            if gap < threshold:
                continue
            value = gap
            desc = (
                f"Current rent ${unit.current_rent} is {gap:.0%} below market ${unit.market_rent}"
            )
            evidence = {
                "current_rent": float(unit.current_rent),
                "market_rent": float(unit.market_rent),
                "gap_pct": round(gap, 4),
                "threshold_pct": threshold,
                "property_id": unit.property_id,
                "property_name": prop_name,
                "unit_number": unit.unit_number,
            }
        else:
            desc = f"{rule.metric} = {value} exceeds threshold {threshold}"
            evidence = {
                "metric": rule.metric,
                "value": value,
                "threshold": threshold,
                "unit_id": unit.id,
            }

        signals.append(
            make_signal(
                defn=defn,
                entity_id=unit.id,
                entity_name=f"{prop_name} / {unit.unit_number}",
                description=desc,
                evidence=evidence,
            )
        )
    return signals


def _read_unit_metric(unit: Any, metric: str) -> float | None:
    if metric == "days_vacant":
        return unit.days_vacant
    if metric == "rent_gap_pct" and unit.market_rent > 0 and unit.current_rent > 0:
        return float((unit.market_rent - unit.current_rent) / unit.market_rent)
    return None


async def _resolve_manager_id(property_id: str, ps: PropertyStore) -> str:
    prop = await ps.get_property(property_id)
    if prop is None:
        return ""
    portfolios = await ps.list_portfolios()
    for pf in portfolios:
        if pf.id == prop.portfolio_id:
            return pf.manager_id
    return ""
