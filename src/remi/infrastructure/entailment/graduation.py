"""HypothesisGraduator — promotes confirmed hypotheses into the live TBox.

When a hypothesis is confirmed (by a human or the director agent), the
graduator translates it into the appropriate TBox entry:

- SIGNAL_DEFINITION → a SignalDefinition added to the runtime DomainOntology
- CAUSAL_CHAIN → a CausalChain + link in the OntologyStore
- ANOMALY_PATTERN / CORRELATION → codified knowledge in the OntologyStore

This is the bridge between induction (PatternDetector proposing candidate
laws) and deduction (EntailmentEngine evaluating them). Once graduated,
a hypothesis's proposed law becomes part of the system's known physics
and is evaluated on every subsequent entailment run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from remi.domain.ontology.types import KnowledgeProvenance
from remi.domain.signals.hypothesis import (
    Hypothesis,
    HypothesisKind,
    HypothesisStatus,
    HypothesisStore,
)
from remi.domain.signals.types import (
    CausalChain,
    DomainOntology,
    Horizon,
    InferenceRule,
    RuleCondition,
    Severity,
    SignalDefinition,
)

if TYPE_CHECKING:
    from remi.domain.ontology.ports import OntologyStore

_log = structlog.get_logger(__name__)


@dataclass
class GraduationResult:
    """What happened when we tried to graduate a hypothesis."""

    hypothesis_id: str
    graduated: bool = False
    tbox_entries_created: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


class HypothesisGraduator:
    """Promotes confirmed hypotheses into live TBox entries.

    Takes a MutableDomainOntology and OntologyStore, translates the
    hypothesis's proposed_tbox_entry into the appropriate typed model,
    and registers it.
    """

    def __init__(
        self,
        domain: MutableDomainOntology,
        ontology_store: OntologyStore,
        hypothesis_store: HypothesisStore,
    ) -> None:
        self._domain = domain
        self._os = ontology_store
        self._hs = hypothesis_store

    async def graduate(self, hypothesis_id: str) -> GraduationResult:
        """Graduate a single confirmed hypothesis into the TBox."""
        result = GraduationResult(hypothesis_id=hypothesis_id)

        hyp = await self._hs.get(hypothesis_id)
        if hyp is None:
            result.reason = "hypothesis not found"
            return result

        if hyp.status != HypothesisStatus.CONFIRMED:
            result.reason = f"hypothesis is {hyp.status.value}, not confirmed"
            return result

        try:
            if hyp.kind == HypothesisKind.SIGNAL_DEFINITION:
                entry = self._graduate_signal_definition(hyp)
                result.tbox_entries_created.append(entry)
            elif hyp.kind == HypothesisKind.CAUSAL_CHAIN:
                entry = await self._graduate_causal_chain(hyp)
                result.tbox_entries_created.append(entry)
            elif hyp.kind in (
                HypothesisKind.ANOMALY_PATTERN,
                HypothesisKind.CORRELATION,
                HypothesisKind.THRESHOLD_ADJUSTMENT,
            ):
                entry = await self._graduate_codified_knowledge(hyp)
                result.tbox_entries_created.append(entry)

            result.graduated = True
            _log.info(
                "hypothesis_graduated",
                hypothesis_id=hypothesis_id,
                kind=hyp.kind.value,
                entries_created=len(result.tbox_entries_created),
            )
        except Exception as exc:
            result.reason = str(exc)
            _log.warning(
                "hypothesis_graduation_failed",
                hypothesis_id=hypothesis_id,
                exc_info=True,
            )

        return result

    async def graduate_all_confirmed(self) -> list[GraduationResult]:
        """Graduate all hypotheses with status=CONFIRMED."""
        confirmed = await self._hs.list_hypotheses(status="confirmed")
        results: list[GraduationResult] = []
        for hyp in confirmed:
            r = await self.graduate(hyp.hypothesis_id)
            results.append(r)
        return results

    def _graduate_signal_definition(self, hyp: Hypothesis) -> dict[str, Any]:
        """Turn a confirmed threshold hypothesis into a live SignalDefinition."""
        proposed = hyp.proposed_tbox_entry
        rule_data = proposed.get("rule", {})

        condition_str = rule_data.get("condition", "exceeds_threshold")
        try:
            condition = RuleCondition(condition_str)
        except ValueError:
            condition = RuleCondition.EXCEEDS_THRESHOLD

        entity_str = proposed.get("entity", "Property")

        threshold_key = f"learned:{proposed.get('name', hyp.hypothesis_id)}"
        threshold_value = rule_data.get("threshold_value", 0.0)
        self._domain.set_threshold(threshold_key, threshold_value)

        defn = SignalDefinition(
            name=proposed.get("name", f"learned_{hyp.hypothesis_id}"),
            description=proposed.get("description", hyp.description),
            severity=Severity.LOW,
            entity=entity_str,
            horizon=Horizon.CURRENT,
            rule=InferenceRule(
                metric=rule_data.get("metric", ""),
                condition=condition,
                threshold_key=threshold_key,
            ),
        )

        self._domain.add_signal(defn)

        return {
            "type": "signal_definition",
            "name": defn.name,
            "threshold_key": threshold_key,
            "threshold_value": threshold_value,
        }

    async def _graduate_causal_chain(self, hyp: Hypothesis) -> dict[str, Any]:
        """Turn a confirmed correlation hypothesis into a CausalChain."""
        proposed = hyp.proposed_tbox_entry
        chain = CausalChain(
            cause=proposed.get("cause", ""),
            effect=proposed.get("effect", ""),
            description=proposed.get("description", hyp.description),
        )

        self._domain.add_causal_chain(chain)

        source_id = f"cause:{chain.cause}"
        target_id = f"cause:{chain.effect}"
        await self._os.codify(
            "cause",
            {"description": chain.description},
            provenance=KnowledgeProvenance.LEARNED,
        )
        await self._os.put_link(
            source_id, "CAUSES", target_id,
            properties={"description": chain.description},
        )

        return {
            "type": "causal_chain",
            "cause": chain.cause,
            "effect": chain.effect,
        }

    async def _graduate_codified_knowledge(self, hyp: Hypothesis) -> dict[str, Any]:
        """Codify a pattern or observation into the OntologyStore."""
        await self._os.codify(
            "hypothesis_observation",
            {
                "title": hyp.title,
                "description": hyp.description,
                "evidence": hyp.evidence,
                "kind": hyp.kind.value,
            },
            provenance=KnowledgeProvenance.LEARNED,
        )
        return {
            "type": "codified_knowledge",
            "title": hyp.title,
            "kind": hyp.kind.value,
        }


class MutableDomainOntology:
    """Runtime-writable view over a frozen DomainOntology.

    The static DomainOntology (from domain.yaml) is immutable — correct
    for hand-authored expert knowledge. This wrapper adds a mutable layer
    for hypotheses that have been confirmed and graduated into the TBox.

    The EntailmentEngine queries this instead of the raw DomainOntology,
    seeing both the static and learned entries.
    """

    def __init__(self, base: DomainOntology) -> None:
        self._base = base
        self._extra_signals: dict[str, SignalDefinition] = {}
        self._extra_thresholds: dict[str, float] = {}
        self._extra_chains: list[CausalChain] = []

    @property
    def base(self) -> DomainOntology:
        return self._base

    @property
    def signals(self) -> dict[str, SignalDefinition]:
        merged = dict(self._base.signals)
        merged.update(self._extra_signals)
        return merged

    @property
    def thresholds(self) -> dict[str, float]:
        merged = dict(self._base.thresholds)
        merged.update(self._extra_thresholds)
        return merged

    @property
    def causal_chains(self) -> list[CausalChain]:
        return list(self._base.causal_chains) + list(self._extra_chains)

    @property
    def policies(self) -> list:
        return list(self._base.policies)

    @property
    def workflows(self) -> list:
        return list(self._base.workflows)

    def threshold(self, key: str, default: float = 0.0) -> float:
        if key in self._extra_thresholds:
            return self._extra_thresholds[key]
        return self._base.threshold(key, default)

    def signals_for_entity(self, entity: str) -> list[SignalDefinition]:
        base = self._base.signals_for_entity(entity)
        extra = [d for d in self._extra_signals.values() if d.entity == entity]
        return base + extra

    def signal(self, name: str) -> SignalDefinition | None:
        if name in self._extra_signals:
            return self._extra_signals[name]
        return self._base.signal(name)

    def policies_for_trigger(self, trigger: str):
        return self._base.policies_for_trigger(trigger)

    def policies_for_signal(self, signal_name: str):
        return self._base.policies_for_signal(signal_name)

    def causal_parents(self, effect: str) -> list[CausalChain]:
        base = self._base.causal_parents(effect)
        extra = [c for c in self._extra_chains if c.effect == effect]
        return base + extra

    def causal_children(self, cause: str) -> list[CausalChain]:
        base = self._base.causal_children(cause)
        extra = [c for c in self._extra_chains if c.cause == cause]
        return base + extra

    def all_signal_names(self) -> list[str]:
        return list(self.signals.keys())

    def add_signal(self, defn: SignalDefinition) -> None:
        self._extra_signals[defn.name] = defn

    def set_threshold(self, key: str, value: float) -> None:
        self._extra_thresholds[key] = value

    def add_causal_chain(self, chain: CausalChain) -> None:
        self._extra_chains.append(chain)

    @property
    def learned_signal_count(self) -> int:
        return len(self._extra_signals)

    @property
    def learned_chain_count(self) -> int:
        return len(self._extra_chains)
