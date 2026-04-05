"""CompositionProducer — emits composite signals when constituents co-occur.

Runs *after* rule-based and statistical producers in the CompositeProducer
pipeline. Reads already-produced signals from the SignalStore and checks
each CompositionRule: if all constituent signal types are active on the
same entity, a composite signal is emitted at the rule's severity.

No LLM calls. Pure rule evaluation over existing signals.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

from remi.agent.graph.types import KnowledgeProvenance
from remi.agent.signals.persistence.stores import SignalStore
from remi.agent.signals.signal import ProducerResult, Signal, SignalProducer
from remi.agent.signals.signal import signal_id as _signal_id
from remi.agent.signals.tbox import CompositionRule, DomainTBox, MutableTBox

_log = structlog.get_logger(__name__)


class CompositionProducer(SignalProducer):
    """Derives composite signals from co-occurring constituent signals."""

    def __init__(
        self,
        domain: DomainTBox | MutableTBox,
        signal_store: SignalStore,
    ) -> None:
        self._domain = domain
        self._ss = signal_store

    @property
    def name(self) -> str:
        return "composition"

    async def evaluate(self) -> ProducerResult:
        result = ProducerResult(source=self.name)
        compositions: list[CompositionRule] = getattr(self._domain, "compositions", [])
        if not compositions:
            return result

        existing = await self._ss.list_signals()
        if not existing:
            return result

        entity_signals: dict[str, dict[str, Signal]] = defaultdict(dict)
        for sig in existing:
            entity_signals[sig.entity_id][sig.signal_type] = sig

        for rule in compositions:
            matches = self._find_matches(rule, entity_signals)
            for entity_id, constituents in matches:
                composite = self._build_composite(rule, entity_id, constituents)
                result.signals.append(composite)
                result.produced += 1
                _log.info(
                    "composite_signal_produced",
                    signal_type=rule.name,
                    entity_id=entity_id,
                    severity=rule.severity.value,
                    constituent_count=len(constituents),
                )

        return result

    def _find_matches(
        self,
        rule: CompositionRule,
        entity_signals: dict[str, dict[str, Signal]],
    ) -> list[tuple[str, list[Signal]]]:
        """Find entities where all constituent signals are active."""
        matches: list[tuple[str, list[Signal]]] = []

        if not rule.require_same_entity:
            return matches

        required = set(rule.constituents)

        for entity_id, type_map in entity_signals.items():
            present = required & type_map.keys()
            if present == required:
                if rule.scope:
                    first = type_map[next(iter(present))]
                    if first.entity_type != rule.scope:
                        continue
                constituents = [type_map[t] for t in rule.constituents]
                matches.append((entity_id, constituents))

        return matches

    def _build_composite(
        self,
        rule: CompositionRule,
        entity_id: str,
        constituents: list[Signal],
    ) -> Signal:
        constituent_descs = "; ".join(
            f"{s.signal_type}: {s.description[:80]}" for s in constituents
        )
        description = f"{rule.description.strip()} [{constituent_descs}]"

        evidence: dict[str, Any] = {
            "composition_rule": rule.name,
            "constituent_signal_ids": [s.signal_id for s in constituents],
            "constituent_types": [s.signal_type for s in constituents],
        }

        entity_name = constituents[0].entity_name if constituents else ""

        return Signal(
            signal_id=_signal_id(rule.name, entity_id),
            signal_type=rule.name,
            severity=rule.severity,
            entity_type=rule.scope or (constituents[0].entity_type if constituents else ""),
            entity_id=entity_id,
            entity_name=entity_name,
            description=description,
            evidence=evidence,
            provenance=KnowledgeProvenance.DATA_DERIVED,
        )
