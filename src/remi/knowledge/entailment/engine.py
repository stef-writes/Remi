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
from typing import Any

import structlog

from remi.knowledge.entailment.base import EntailmentResult
from remi.knowledge.entailment.base import signal_id as _signal_id
from remi.knowledge.entailment.delinquency import eval_manager_delinquency
from remi.knowledge.entailment.existence import eval_exists, eval_in_legal_track
from remi.knowledge.entailment.lease import eval_breach_detected, eval_manager_lease_cliff
from remi.knowledge.entailment.maintenance import eval_manager_maintenance_backlog
from remi.knowledge.entailment.portfolio import (
    eval_below_percentile,
    eval_manager_concentration_risk,
)
from remi.knowledge.entailment.threshold import eval_unit_threshold
from remi.knowledge.entailment.trend import (
    eval_consistent_direction,
    eval_declining_consecutive_periods,
)
from remi.models.properties import PropertyStore
from remi.models.signals import (
    DomainOntology,
    ProducerResult,
    RuleCondition,
    Signal,
    SignalDefinition,
    SignalProducer,
    SignalStore,
)
from remi.models.trace import SpanKind
from remi.observability.tracer import Tracer
from remi.services.snapshots import SnapshotService

_log = structlog.get_logger(__name__)


class EntailmentEngine(SignalProducer):
    """Rule-based signal producer — derives signals from TBox rules applied to ABox facts."""

    def __init__(
        self,
        domain: DomainOntology,
        property_store: PropertyStore,
        signal_store: SignalStore | None = None,
        tracer: Tracer | None = None,
        snapshot_service: SnapshotService | None = None,
    ) -> None:
        self._domain = domain  # type: ignore[assignment]
        self._ps = property_store
        self._ss = signal_store
        self._tracer = tracer
        self._snapshots = snapshot_service

        self._evaluators: dict[
            RuleCondition,
            Callable[[SignalDefinition], Coroutine[Any, Any, list[Signal]]],
        ] = {  # bound methods — each one wraps an evaluator function
            RuleCondition.EXCEEDS_THRESHOLD: self._eval_exceeds_threshold,
            RuleCondition.AGING_PAST_THRESHOLD: self._eval_aging_past_threshold,
            RuleCondition.IN_LEGAL_TRACK: self._eval_in_legal_track,
            RuleCondition.DECLINING_CONSECUTIVE_PERIODS: self._eval_declining_consecutive_periods,
            RuleCondition.BELOW_PERCENTILE: self._eval_below_percentile,
            RuleCondition.CONSISTENT_DIRECTION: self._eval_consistent_direction,
            RuleCondition.EXISTS: self._eval_exists,
            RuleCondition.BREACH_DETECTED: self._eval_breach_detected,
        }

    # -- SignalProducer interface -----------------------------------------------

    @property
    def name(self) -> str:
        return "rule_engine"

    async def evaluate(self) -> ProducerResult:
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

    # -- Legacy run_all (backward compatibility) --------------------------------

    async def run_all(self) -> EntailmentResult:
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

        _log.info("entailment_complete", produced=result.produced, retired=result.retired)
        return result

    async def _run_all_traced(self) -> EntailmentResult:
        assert self._tracer is not None
        assert self._ss is not None, "run_all() requires signal_store"
        async with self._tracer.start_trace(
            "entailment.run_all",
            kind=SpanKind.ENTAILMENT,
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

    # -- Dispatch wrappers (bind evaluator modules to self) --------------------

    async def _eval_exceeds_threshold(self, defn: SignalDefinition) -> list[Signal]:
        rule = defn.rule
        metric = rule.metric
        if defn.entity == "Unit":
            return await eval_unit_threshold(defn, self._domain, self._ps, self._make_signal)
        elif defn.entity == "PropertyManager":
            if metric == "delinquency_rate":
                return await eval_manager_delinquency(
                    defn, self._domain, self._ps, self._make_signal
                )
            elif metric == "expiring_lease_pct":
                return await eval_manager_lease_cliff(
                    defn, self._domain, self._ps, self._make_signal
                )
            elif metric == "concentration_pct":
                return await eval_manager_concentration_risk(
                    defn, self._domain, self._ps, self._make_signal
                )
        return []

    async def _eval_aging_past_threshold(self, defn: SignalDefinition) -> list[Signal]:
        if defn.rule.metric == "open_work_orders":
            return await eval_manager_maintenance_backlog(
                defn, self._domain, self._ps, self._make_signal
            )
        return []

    async def _eval_in_legal_track(self, defn: SignalDefinition) -> list[Signal]:
        return await eval_in_legal_track(defn, self._ps, self._make_signal)

    async def _eval_declining_consecutive_periods(self, defn: SignalDefinition) -> list[Signal]:
        return await eval_declining_consecutive_periods(
            defn, self._ps, self._snapshots, self._make_signal
        )

    async def _eval_below_percentile(self, defn: SignalDefinition) -> list[Signal]:
        return await eval_below_percentile(defn, self._domain, self._ps, self._make_signal)

    async def _eval_consistent_direction(self, defn: SignalDefinition) -> list[Signal]:
        return await eval_consistent_direction(defn, self._ps, self._snapshots, self._make_signal)

    async def _eval_exists(self, defn: SignalDefinition) -> list[Signal]:
        return await eval_exists(defn, self._ps, self._make_signal)

    async def _eval_breach_detected(self, defn: SignalDefinition) -> list[Signal]:
        return await eval_breach_detected(defn, self._domain, self._ps, self._make_signal)

    # -- Signal factory --------------------------------------------------------

    def _make_signal(
        self,
        defn: SignalDefinition,
        entity_id: str,
        entity_name: str,
        description: str,
        evidence: dict[str, Any],
    ) -> Signal:
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
