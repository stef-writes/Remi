"""EntailmentEngine — evaluates TBox rules against ABox facts to derive signals.

Rule-driven: the engine iterates every SignalDefinition in the DomainOntology,
reads its InferenceRule, dispatches on the RuleCondition enum, and produces
Signal instances. Adding a new signal to domain.yaml is sufficient for any
condition the engine already understands. No per-signal Python methods.

Implements the ``SignalProducer`` port so it can be composed with statistical
and learned producers via ``CompositeProducer``.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from remi.domain.properties.ports import PropertyStore
from remi.domain.signals.ports import SignalStore
from remi.domain.signals.producers import ProducerResult, SignalProducer
from remi.domain.signals.types import (
    DomainOntology,
    Provenance,
    RuleCondition,
    Signal,
    SignalDefinition,
)
from remi.domain.trace.types import SpanKind
from remi.infrastructure.trace.tracer import Tracer

if TYPE_CHECKING:
    from remi.application.snapshots.service import SnapshotService

_log = structlog.get_logger(__name__)


def _signal_id(signal_type: str, entity_id: str) -> str:
    return f"signal:{signal_type.lower()}:{entity_id}"


@dataclass
class EntailmentResult:
    """Result type for ``EntailmentEngine.run_all()``.

    The composite pipeline uses ``CompositeResult`` instead; this type is
    specific to the rule-based engine's direct ``run_all()`` path.
    """

    produced: int = 0
    retired: int = 0
    unchanged: int = 0
    signals: list[Signal] = field(default_factory=list)
    trace_id: str | None = None


class EntailmentEngine(SignalProducer):
    """Rule-based signal producer — derives signals from TBox rules applied to ABox facts.

    For each SignalDefinition, the engine dispatches on
    ``definition.rule.condition`` to a generic evaluator. The evaluator
    knows how to query the PropertyStore for the relevant entity type
    and apply the rule's parameters (threshold_key, window, etc.).

    Implements ``SignalProducer`` so it plugs into ``CompositeProducer``.
    Also retains its own ``run_all()`` for backward compatibility.
    """

    def __init__(
        self,
        domain: DomainOntology,
        property_store: PropertyStore,
        signal_store: SignalStore | None = None,
        tracer: Tracer | None = None,
        snapshot_service: SnapshotService | None = None,
    ) -> None:
        self._domain = domain  # type: ignore[assignment]  # accepts MutableDomainOntology
        self._ps = property_store
        self._ss = signal_store
        self._tracer = tracer
        self._snapshots = snapshot_service

        self._evaluators: dict[
            RuleCondition,
            Callable[[SignalDefinition], Coroutine[Any, Any, list[Signal]]],
        ] = {
            RuleCondition.EXCEEDS_THRESHOLD: self._eval_exceeds_threshold,
            RuleCondition.AGING_PAST_THRESHOLD: self._eval_aging_past_threshold,
            RuleCondition.IN_LEGAL_TRACK: self._eval_in_legal_track,
            RuleCondition.DECLINING_CONSECUTIVE_PERIODS: self._eval_declining_consecutive_periods,
            RuleCondition.BELOW_PERCENTILE: self._eval_below_percentile,
            RuleCondition.CONSISTENT_DIRECTION: self._eval_consistent_direction,
            RuleCondition.EXISTS: self._eval_exists,
            RuleCondition.BREACH_DETECTED: self._eval_breach_detected,
        }

    # -- SignalProducer interface ----------------------------------------------

    @property
    def name(self) -> str:
        return "rule_engine"

    async def evaluate(self) -> ProducerResult:
        """SignalProducer implementation — evaluate all rules, return results."""
        result = ProducerResult(source=self.name)
        for defn in self._domain.signals.values():
            evaluator = self._evaluators.get(defn.rule.condition)
            if evaluator is None:
                _log.warning(
                    "no_evaluator_for_condition",
                    signal=defn.name,
                    condition=defn.rule.condition.value,
                )
                continue
            try:
                signals = await evaluator(defn)
                for sig in signals:
                    result.signals.append(sig)
                    result.produced += 1
            except Exception:
                result.errors += 1
                _log.warning(
                    "entailment_evaluator_failed",
                    signal=defn.name,
                    condition=defn.rule.condition.value,
                    exc_info=True,
                )
        return result

    # -- Legacy run_all (backward compatibility) ------------------------------

    async def run_all(self) -> EntailmentResult:
        """Evaluate every SignalDefinition in the TBox.

        Backward-compatible entry point. When using CompositeProducer,
        call ``evaluate()`` instead — the composite handles SignalStore writes.
        """
        if self._tracer is not None:
            return await self._run_all_traced()
        return await self._run_all_core()

    async def _run_all_core(self) -> EntailmentResult:
        assert self._ss is not None, "run_all() requires signal_store"
        await self._ss.clear_all()

        pr = await self.evaluate()
        result = EntailmentResult(produced=pr.produced)

        for sig in pr.signals:
            await self._ss.put_signal(sig)
            result.signals.append(sig)
            _log.info(
                "signal_produced",
                signal_type=sig.signal_type,
                entity_id=sig.entity_id,
                severity=sig.severity.value,
            )

        _log.info(
            "entailment_complete",
            produced=result.produced,
            retired=result.retired,
        )
        return result

    async def _run_all_traced(self) -> EntailmentResult:
        assert self._tracer is not None
        assert self._ss is not None, "run_all() requires signal_store"
        async with self._tracer.start_trace(
            "entailment.run_all", kind=SpanKind.ENTAILMENT,
            signal_definitions=len(self._domain.signals),
            thresholds=dict(self._domain.thresholds),
            policy_count=len(self._domain.policies),
            causal_chain_count=len(self._domain.causal_chains),
        ) as trace_ctx:
            await self._ss.clear_all()
            result = EntailmentResult()
            result.trace_id = trace_ctx.trace_id

            for defn in self._domain.signals.values():
                evaluator = self._evaluators.get(defn.rule.condition)

                async with trace_ctx.span(
                    SpanKind.ENTAILMENT,
                    f"evaluate:{defn.name}",
                    signal_name=defn.name,
                    entity_type=defn.entity,
                    severity=defn.severity.value,
                    condition=defn.rule.condition.value,
                    metric=defn.rule.metric,
                    threshold_key=defn.rule.threshold_key,
                ) as eval_ctx:
                    if evaluator is None:
                        eval_ctx.set_attribute("skipped", True)
                        eval_ctx.set_attribute("reason", "no_evaluator")
                        continue

                    try:
                        signals = await evaluator(defn)
                        eval_ctx.set_attribute("signals_produced", len(signals))
                        for sig in signals:
                            await self._ss.put_signal(sig)
                            result.signals.append(sig)
                            result.produced += 1
                            eval_ctx.add_event(
                                "signal_produced",
                                signal_type=sig.signal_type,
                                entity_id=sig.entity_id,
                                entity_name=sig.entity_name,
                                severity=sig.severity.value,
                                description=sig.description,
                            )
                    except Exception as exc:
                        eval_ctx.set_attribute("error", str(exc))
                        _log.warning(
                            "entailment_evaluator_failed",
                            signal=defn.name,
                            condition=defn.rule.condition.value,
                            exc_info=True,
                        )

            trace_ctx.set_attribute("total_produced", result.produced)
            _log.info(
                "entailment_complete",
                produced=result.produced,
                trace_id=trace_ctx.trace_id,
            )
            return result

    # -- Generic evaluators dispatched by RuleCondition -----------------------

    async def _eval_exceeds_threshold(self, defn: SignalDefinition) -> list[Signal]:
        """Generic: fires when a metric exceeds a TBox threshold.

        Works for Unit-scoped and Manager-scoped signals. The metric
        name determines which data path to use.
        """
        rule = defn.rule
        metric = rule.metric

        if defn.entity == "Unit":
            return await self._eval_unit_threshold(defn)
        elif defn.entity == "PropertyManager":
            if metric == "delinquency_rate":
                return await self._eval_manager_delinquency(defn)
            elif metric == "expiring_lease_pct":
                return await self._eval_manager_lease_cliff(defn)
            elif metric == "concentration_pct":
                return await self._eval_manager_concentration_risk(defn)
        return []

    async def _eval_aging_past_threshold(self, defn: SignalDefinition) -> list[Signal]:
        """Generic: fires when items age past a day threshold."""
        if defn.rule.metric == "open_work_orders":
            return await self._eval_manager_maintenance_backlog(defn)
        return []

    async def _eval_in_legal_track(self, defn: SignalDefinition) -> list[Signal]:
        """Generic: fires when an entity matches a set of statuses."""
        statuses = set(defn.rule.statuses or [])
        if not statuses:
            return []

        tenants = await self._ps.list_tenants()
        signals: list[Signal] = []

        for t in tenants:
            if t.status.value in statuses:
                signals.append(self._make_signal(
                    defn=defn,
                    entity_id=t.id,
                    entity_name=t.name,
                    description=f"Tenant in legal/eviction track",
                    evidence={
                        "tenant_status": t.status.value,
                        "balance_owed": float(t.balance_owed),
                        "tenant_name": t.name,
                    },
                ))
        return signals

    async def _eval_declining_consecutive_periods(
        self, defn: SignalDefinition,
    ) -> list[Signal]:
        """Fires when a manager's metric declines over N consecutive snapshot periods.

        Uses SnapshotService history. Falls back gracefully if no snapshots exist.
        """
        if self._snapshots is None:
            _log.debug("no_snapshot_service", signal=defn.name)
            return []

        required_periods = defn.rule.periods or 2
        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            history = self._snapshots.get_history(mgr.id)
            if len(history) < required_periods + 1:
                continue

            recent = sorted(history, key=lambda s: s.timestamp, reverse=True)
            values = [s.occupancy_rate for s in recent[: required_periods + 1]]

            declining_count = sum(
                1 for i in range(len(values) - 1) if values[i] < values[i + 1]
            )
            if declining_count >= required_periods:
                drop = values[-1] - values[0]
                signals.append(self._make_signal(
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
                        "timestamps": [s.timestamp.isoformat() for s in recent[: required_periods + 1]],
                        "manager_id": mgr.id,
                    },
                ))
        return signals

    async def _eval_below_percentile(
        self, defn: SignalDefinition,
    ) -> list[Signal]:
        """Fires when a manager's composite metric is below the Nth percentile of peers."""
        percentile = defn.rule.percentile or 25
        managers = await self._ps.list_managers()
        if len(managers) < 2:
            return []

        scores: list[tuple[Any, float]] = []
        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            total_units = 0
            occupied = 0
            total_rent = Decimal("0")
            total_owed = Decimal("0")

            for pf in portfolios:
                properties = await self._ps.list_properties(portfolio_id=pf.id)
                for prop in properties:
                    units = await self._ps.list_units(property_id=prop.id)
                    for u in units:
                        total_units += 1
                        if u.status.value == "occupied":
                            occupied += 1
                        total_rent += u.current_rent
                    tenants = await self._ps.list_tenants(property_id=prop.id)
                    for t in tenants:
                        total_owed += t.balance_owed

            occ_rate = occupied / total_units if total_units else 0.0
            delinq_penalty = (
                float(total_owed / total_rent) if total_rent > 0 else 0.0
            )
            composite = occ_rate - delinq_penalty
            scores.append((mgr, composite))

        scores.sort(key=lambda x: x[1])
        cutoff_idx = max(1, len(scores) * percentile // 100)
        cutoff_value = scores[cutoff_idx - 1][1] if scores else 0.0

        signals: list[Signal] = []
        for mgr, score in scores[:cutoff_idx]:
            rank = next(i + 1 for i, (m, _) in enumerate(scores) if m.id == mgr.id)
            signals.append(self._make_signal(
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
            ))
        return signals

    async def _eval_consistent_direction(
        self, defn: SignalDefinition,
    ) -> list[Signal]:
        """Fires when a manager's metrics move consistently in one direction.

        Uses SnapshotService history to detect sustained improvement or decline.
        """
        if self._snapshots is None:
            _log.debug("no_snapshot_service", signal=defn.name)
            return []

        required_periods = defn.rule.periods or 2
        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            history = self._snapshots.get_history(mgr.id)
            if len(history) < required_periods + 1:
                continue

            recent = sorted(history, key=lambda s: s.timestamp, reverse=True)
            snapshots = recent[: required_periods + 1]
            occ_values = [s.occupancy_rate for s in snapshots]
            rent_values = [s.total_rent for s in snapshots]

            occ_deltas = [occ_values[i] - occ_values[i + 1] for i in range(len(occ_values) - 1)]
            rent_deltas = [rent_values[i] - rent_values[i + 1] for i in range(len(rent_values) - 1)]

            all_improving = all(d > 0 for d in occ_deltas) or all(d > 0 for d in rent_deltas)
            all_declining = all(d < 0 for d in occ_deltas) or all(d < 0 for d in rent_deltas)

            if not all_improving and not all_declining:
                continue

            direction = "improving" if all_improving else "declining"
            signals.append(self._make_signal(
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
                    "timestamps": [s.timestamp.isoformat() for s in snapshots],
                    "manager_id": mgr.id,
                },
            ))
        return signals

    async def _eval_exists(self, defn: SignalDefinition) -> list[Signal]:
        """Fires when unreported situations exist in the data.

        Heuristic: finds tenants with aging balances (30+ days), properties
        with high vacancy counts, or tenants in legal track with large
        balances — situations the director should know about.
        """
        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            unreported: list[dict[str, Any]] = []

            for pf in portfolios:
                properties = await self._ps.list_properties(portfolio_id=pf.id)
                for prop in properties:
                    tenants = await self._ps.list_tenants(property_id=prop.id)
                    for t in tenants:
                        if t.balance_30_plus > 0 and t.balance_30_plus >= Decimal("500"):
                            unreported.append({
                                "type": "aging_balance",
                                "tenant_id": t.id,
                                "tenant_name": t.name,
                                "balance_30_plus": float(t.balance_30_plus),
                                "total_owed": float(t.balance_owed),
                                "property_id": prop.id,
                                "property_name": prop.name,
                            })

                    units = await self._ps.list_units(property_id=prop.id)
                    vacant_units = [
                        u for u in units
                        if u.status.value == "vacant"
                        and u.days_vacant is not None
                        and u.days_vacant > 14
                    ]
                    if len(vacant_units) >= 3:
                        unreported.append({
                            "type": "high_vacancy_cluster",
                            "property_id": prop.id,
                            "property_name": prop.name,
                            "vacant_count": len(vacant_units),
                            "avg_days_vacant": round(
                                sum(u.days_vacant or 0 for u in vacant_units)
                                / len(vacant_units)
                            ),
                        })

            if unreported:
                unreported.sort(
                    key=lambda r: r.get("balance_30_plus", 0) or r.get("vacant_count", 0),
                    reverse=True,
                )
                signals.append(self._make_signal(
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
                ))
        return signals

    async def _eval_breach_detected(self, defn: SignalDefinition) -> list[Signal]:
        """Fires when required policy actions haven't happened within deadlines.

        Checks:
        - Renewal offers: leases expiring within renewal_outreach_days with no
          renewal (pending) lease on the same unit.
        - Make-ready deadlines: vacant units with open maintenance orders past
          the make_ready_deadline_days threshold.
        """
        renewal_window = int(self._domain.threshold("renewal_outreach_days_before", 90))
        make_ready_days = int(self._domain.threshold("make_ready_deadline_days", 14))
        cutoff = date.today() + timedelta(days=renewal_window)
        now = datetime.now(UTC)

        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            breaches: list[dict[str, Any]] = []

            for pf in portfolios:
                properties = await self._ps.list_properties(portfolio_id=pf.id)
                for prop in properties:
                    leases = await self._ps.list_leases(property_id=prop.id)
                    active = [l for l in leases if l.status.value == "active"]
                    pending_units = {
                        l.unit_id for l in leases if l.status.value == "pending"
                    }

                    for lease in active:
                        if lease.end_date <= cutoff and lease.unit_id not in pending_units:
                            days_until = (lease.end_date - date.today()).days
                            breaches.append({
                                "type": "renewal_not_sent",
                                "lease_id": lease.id,
                                "unit_id": lease.unit_id,
                                "end_date": lease.end_date.isoformat(),
                                "days_until_expiry": days_until,
                                "monthly_rent": float(lease.monthly_rent),
                                "property_id": prop.id,
                                "property_name": prop.name,
                            })

                    units = await self._ps.list_units(property_id=prop.id)
                    vacant_units = [
                        u for u in units if u.status.value == "vacant"
                    ]
                    maint = await self._ps.list_maintenance_requests(
                        property_id=prop.id
                    )
                    open_maint_by_unit = {}
                    for req in maint:
                        if req.status.value in ("open", "in_progress"):
                            age = (now - req.created_at).days
                            if age > make_ready_days:
                                open_maint_by_unit.setdefault(req.unit_id, []).append(req)

                    for vu in vacant_units:
                        overdue = open_maint_by_unit.get(vu.id)
                        if overdue:
                            breaches.append({
                                "type": "make_ready_overdue",
                                "unit_id": vu.id,
                                "unit_number": vu.unit_number,
                                "property_id": prop.id,
                                "property_name": prop.name,
                                "overdue_orders": len(overdue),
                                "oldest_days": max(
                                    (now - r.created_at).days for r in overdue
                                ),
                            })

            if breaches:
                breaches.sort(
                    key=lambda b: b.get("days_until_expiry", 999),
                )
                signals.append(self._make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{len(breaches)} policy breach(es) detected: "
                        f"{sum(1 for b in breaches if b['type'] == 'renewal_not_sent')} "
                        f"renewal(s) not sent, "
                        f"{sum(1 for b in breaches if b['type'] == 'make_ready_overdue')} "
                        f"make-ready overdue"
                    ),
                    evidence={
                        "breach_count": len(breaches),
                        "breaches": breaches[:20],
                        "manager_id": mgr.id,
                    },
                ))
        return signals

    # -- Entity-specific data access (called by generic evaluators) -----------

    async def _eval_unit_threshold(self, defn: SignalDefinition) -> list[Signal]:
        """Evaluate a threshold rule against units."""
        rule = defn.rule
        threshold_key = rule.threshold_key or ""
        threshold = self._domain.threshold(threshold_key, 0)
        units = await self._ps.list_units()
        signals: list[Signal] = []

        for unit in units:
            value = self._read_unit_metric(unit, rule.metric)
            if value is None or value <= threshold:
                continue

            prop = await self._ps.get_property(unit.property_id)
            prop_name = prop.name if prop else unit.property_id
            manager_id = await self._resolve_manager_id(unit.property_id)

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
                    f"Current rent ${unit.current_rent} is {gap:.0%} "
                    f"below market ${unit.market_rent}"
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

            signals.append(self._make_signal(
                defn=defn,
                entity_id=unit.id,
                entity_name=f"{prop_name} / {unit.unit_number}",
                description=desc,
                evidence=evidence,
            ))
        return signals

    async def _eval_manager_delinquency(self, defn: SignalDefinition) -> list[Signal]:
        threshold_key = defn.rule.threshold_key or "delinquency_critical_pct"
        critical_pct = self._domain.threshold(threshold_key, 0.08)
        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            total_rent = Decimal("0")
            total_owed = Decimal("0")
            delinquent_tenants: list[dict[str, Any]] = []

            for pf in portfolios:
                properties = await self._ps.list_properties(portfolio_id=pf.id)
                for prop in properties:
                    tenants = await self._ps.list_tenants(property_id=prop.id)
                    leases = await self._ps.list_leases(property_id=prop.id)
                    active_rents = {
                        lease.tenant_id: lease.monthly_rent for lease in leases
                        if lease.status.value == "active"
                    }
                    for t in tenants:
                        rent = active_rents.get(t.id, Decimal("0"))
                        total_rent += rent
                        if t.balance_owed > 0:
                            total_owed += t.balance_owed
                            delinquent_tenants.append({
                                "tenant_id": t.id,
                                "name": t.name,
                                "balance_owed": float(t.balance_owed),
                                "balance_30_plus": float(t.balance_30_plus),
                                "property_id": prop.id,
                                "property_name": prop.name,
                            })

            if total_rent <= 0:
                continue

            rate = float(total_owed / total_rent)
            if rate >= critical_pct:
                delinquent_tenants.sort(key=lambda d: d["balance_owed"], reverse=True)
                signals.append(self._make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"Delinquency rate {rate:.1%} exceeds "
                        f"threshold {critical_pct:.1%}"
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
                ))
        return signals

    async def _eval_manager_lease_cliff(self, defn: SignalDefinition) -> list[Signal]:
        rule = defn.rule
        cliff_pct = self._domain.threshold(rule.threshold_key or "lease_cliff_pct", 0.30)
        window_days = int(self._domain.threshold(rule.window_key or "lease_cliff_window_days", 60))
        cutoff = date.today() + timedelta(days=window_days)

        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            all_leases = []
            for pf in portfolios:
                properties = await self._ps.list_properties(portfolio_id=pf.id)
                for prop in properties:
                    leases = await self._ps.list_leases(property_id=prop.id)
                    all_leases.extend(leases)

            active_leases = [l for l in all_leases if l.status.value == "active"]
            if not active_leases:
                continue

            expiring = [l for l in active_leases if l.end_date <= cutoff]
            expiring_pct = len(expiring) / len(active_leases)

            if expiring_pct >= cliff_pct:
                expiring_details = [
                    {"lease_id": l.id, "unit_id": l.unit_id,
                     "end_date": l.end_date.isoformat(),
                     "monthly_rent": float(l.monthly_rent)}
                    for l in sorted(expiring, key=lambda l: l.end_date)[:20]
                ]
                signals.append(self._make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{len(expiring)} of {len(active_leases)} active leases "
                        f"({expiring_pct:.0%}) expire within {window_days} days"
                    ),
                    evidence={
                        "expiring_count": len(expiring),
                        "total_active": len(active_leases),
                        "expiring_pct": round(expiring_pct, 4),
                        "window_days": window_days,
                        "threshold_pct": cliff_pct,
                        "expiring_leases": expiring_details,
                        "manager_id": mgr.id,
                    },
                ))
        return signals

    async def _eval_manager_maintenance_backlog(self, defn: SignalDefinition) -> list[Signal]:
        threshold_key = defn.rule.threshold_key or "maintenance_backlog_days"
        threshold_days = int(self._domain.threshold(threshold_key, 30))
        now = datetime.now(UTC)
        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            aging_requests: list[dict[str, Any]] = []

            for pf in portfolios:
                properties = await self._ps.list_properties(portfolio_id=pf.id)
                for prop in properties:
                    requests = await self._ps.list_maintenance_requests(
                        property_id=prop.id
                    )
                    for req in requests:
                        if req.status.value in ("open", "in_progress"):
                            age_days = (now - req.created_at).days
                            if age_days > threshold_days:
                                aging_requests.append({
                                    "request_id": req.id,
                                    "title": req.title,
                                    "age_days": age_days,
                                    "priority": req.priority.value,
                                    "property_id": prop.id,
                                    "property_name": prop.name,
                                    "unit_id": req.unit_id,
                                })

            if aging_requests:
                aging_requests.sort(key=lambda r: r["age_days"], reverse=True)
                signals.append(self._make_signal(
                    defn=defn,
                    entity_id=mgr.id,
                    entity_name=mgr.name,
                    description=(
                        f"{len(aging_requests)} work orders open longer than "
                        f"{threshold_days} days"
                    ),
                    evidence={
                        "aging_count": len(aging_requests),
                        "threshold_days": threshold_days,
                        "aging_requests": aging_requests[:20],
                        "manager_id": mgr.id,
                    },
                ))
        return signals

    async def _eval_manager_concentration_risk(self, defn: SignalDefinition) -> list[Signal]:
        """Fires when a single property dominates a manager's revenue stream."""
        threshold_key = defn.rule.threshold_key or "concentration_risk_pct"
        threshold = self._domain.threshold(threshold_key, 0.40)
        managers = await self._ps.list_managers()
        signals: list[Signal] = []

        for mgr in managers:
            portfolios = await self._ps.list_portfolios(manager_id=mgr.id)
            property_revenue: list[tuple[str, str, float]] = []
            total_revenue = Decimal("0")

            for pf in portfolios:
                properties = await self._ps.list_properties(portfolio_id=pf.id)
                for prop in properties:
                    leases = await self._ps.list_leases(property_id=prop.id)
                    prop_rent = sum(
                        (l.monthly_rent for l in leases if l.status.value == "active"),
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
                signals.append(self._make_signal(
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
                ))
        return signals

    # -- Helpers --------------------------------------------------------------

    def _make_signal(
        self,
        defn: SignalDefinition,
        entity_id: str,
        entity_name: str,
        description: str,
        evidence: dict[str, Any],
    ) -> Signal:
        """Construct a Signal from a definition + runtime data."""
        return Signal(
            signal_id=_signal_id(defn.name, entity_id),
            signal_type=defn.name,
            severity=defn.severity,
            entity_type=defn.entity,
            entity_id=entity_id,
            entity_name=entity_name,
            description=description,
            evidence=evidence,
        )

    def _read_unit_metric(self, unit: Any, metric: str) -> float | None:
        if metric == "days_vacant":
            return unit.days_vacant
        if metric == "rent_gap_pct":
            if unit.market_rent > 0 and unit.current_rent > 0:
                return float((unit.market_rent - unit.current_rent) / unit.market_rent)
        return None

    async def _resolve_manager_id(self, property_id: str) -> str:
        prop = await self._ps.get_property(property_id)
        if prop is None:
            return ""
        portfolios = await self._ps.list_portfolios()
        for pf in portfolios:
            if pf.id == prop.portfolio_id:
                return pf.manager_id
        return ""
