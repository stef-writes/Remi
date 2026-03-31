"""GraphRAG context assembly — builds structured context frames for agents.

The ContextBuilder is the bridge between the knowledge infrastructure
(ontology, signals, entailment, graph) and the agent. Instead of the
agent making tool calls to discover context, the ContextBuilder
pre-assembles a rich, typed ContextFrame.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.knowledge.graph_retriever import GraphRetriever, ResolvedEntity
from remi.models.chat import Message
from remi.models.ontology import OntologyLink
from remi.models.signals import (
    CausalChain,
    DomainOntology,
    MutableDomainOntology,
    Policy,
    Signal,
    SignalStore,
)
from remi.models.trace import SpanKind
from remi.observability.tracer import Tracer

_log = structlog.get_logger(__name__)


@dataclass
class ContextFrame:
    """Structured pre-assembled context for an agent run.

    Contains everything the agent needs to reason — entities, signals,
    policies, causal chains, and graph neighborhood — without making
    tool calls to discover it.
    """

    entities: list[ResolvedEntity] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    policies: list[Policy] = field(default_factory=list)
    causal_chains: list[CausalChain] = field(default_factory=list)
    neighborhood: dict[str, list[OntologyLink]] = field(default_factory=dict)
    domain_context: str = ""
    signal_summary: str = ""


class ContextBuilder:
    """Assembles a ContextFrame from the knowledge graph and domain ontology.

    Phases:
    1. Render domain context (TBox → system message block)
    2. Render active signals
    3. Optionally resolve question-relevant entities via GraphRetriever
    """

    def __init__(
        self,
        domain: DomainOntology | MutableDomainOntology,
        signal_store: SignalStore | None = None,
        graph_retriever: GraphRetriever | None = None,
    ) -> None:
        self._domain = domain
        self._signal_store = signal_store
        self._graph_retriever = graph_retriever

    async def build(
        self,
        question: str | None = None,
        *,
        tracer: Tracer | None = None,
    ) -> ContextFrame:
        """Build a full context frame."""
        frame = ContextFrame()

        frame.domain_context = render_domain_context(self._domain)
        if tracer is not None and frame.domain_context:
            async with tracer.span(
                SpanKind.PERCEPTION,
                "tbox_injection",
                signal_definitions=len(getattr(self._domain, "signals", {})),
                threshold_count=len(getattr(self._domain, "thresholds", {})),
                policy_count=len(getattr(self._domain, "policies", [])),
                causal_chain_count=len(getattr(self._domain, "causal_chains", [])),
            ):
                pass

        if self._signal_store is not None:
            frame.signal_summary = await render_active_signals(self._signal_store)
            with contextlib.suppress(Exception):
                frame.signals = await self._signal_store.list_signals()

            if tracer is not None:
                severity_counts: dict[str, int] = {}
                for s in frame.signals:
                    sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
                    severity_counts[sev] = severity_counts.get(sev, 0) + 1
                async with tracer.span(
                    SpanKind.PERCEPTION,
                    "signal_injection",
                    active_signals=len(frame.signals),
                    severity_breakdown=severity_counts,
                    signal_types=[s.signal_type for s in frame.signals][:25],
                ):
                    pass

        frame.policies = list(getattr(self._domain, "policies", []))
        frame.causal_chains = list(getattr(self._domain, "causal_chains", []))

        if self._graph_retriever is not None and question:
            try:
                retrieval = await self._graph_retriever.retrieve(question)
                frame.entities = retrieval.entities
                frame.neighborhood = retrieval.neighborhood
                if retrieval.signals:
                    seen = {s.signal_id for s in frame.signals}
                    for s in retrieval.signals:
                        if s.signal_id not in seen:
                            frame.signals.append(s)
            except Exception:
                _log.debug("graph_retrieval_failed", exc_info=True)

        return frame

    def inject_into_thread(
        self,
        thread: list[Message],
        frame: ContextFrame,
    ) -> None:
        """Inject the context frame into the thread as system messages."""
        insert_idx = 1
        if frame.domain_context:
            thread.insert(insert_idx, Message(role="system", content=frame.domain_context))
            insert_idx += 1
        if frame.signal_summary:
            thread.insert(insert_idx, Message(role="system", content=frame.signal_summary))


def render_domain_context(domain: Any) -> str:
    """Render the TBox into a compact system message block."""
    from remi.models.signals import DomainOntology

    if isinstance(domain, MutableDomainOntology):
        pass
    elif not isinstance(domain, DomainOntology):
        return ""

    parts = ["## Domain Context (from ontology)\n"]

    signals = getattr(domain, "signals", {})
    if signals:
        signal_lines = []
        for defn in signals.values() if isinstance(signals, dict) else signals:
            desc = defn.description.split("\n")[0].strip()
            signal_lines.append(
                f"- **{defn.name}** [{defn.severity.value}] ({defn.entity}): {desc}"
            )
        parts.append("**Signal definitions (what the entailment engine detects):**")
        parts.append("\n".join(signal_lines))

    thresholds = getattr(domain, "thresholds", {})
    if thresholds:
        threshold_lines = [f"- {key}: {val}" for key, val in thresholds.items()]
        parts.append("\n**Operational thresholds:**")
        parts.append("\n".join(threshold_lines))

    policies = getattr(domain, "policies", [])
    if policies:
        policy_lines = [f"- [{pol.deontic.value}] {pol.description}" for pol in policies]
        parts.append("\n**Deontic obligations:**")
        parts.append("\n".join(policy_lines))

    causal_chains = getattr(domain, "causal_chains", [])
    if causal_chains:
        chain_lines = [f"- {c.cause} → {c.effect}: {c.description}" for c in causal_chains]
        parts.append("\n**Known causal relationships:**")
        parts.append("\n".join(chain_lines))

    parts.append(
        "\nWhen you detect data matching any signal definition above, "
        "name it explicitly by its domain signal name. Use causal chains "
        "to connect related signals. Reference policies when recommending actions."
    )
    return "\n".join(parts)


async def render_active_signals(signal_store: Any) -> str:
    """Fetch current signals and render a compact summary for the LLM."""
    try:
        signals = await signal_store.list_signals()
    except Exception:
        return ""

    if not signals:
        return (
            "## Active Signals (0)\n\n"
            "No signals currently active. The portfolio appears within normal parameters. "
            "If the user asks about problems, verify by querying the data directly."
        )

    severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}

    lines = [f"## Active Signals ({len(signals)})\n"]
    for s in signals[:25]:
        sev_val = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
        icon = severity_icon.get(sev_val, "❓")
        lines.append(
            f"- {icon} **[{sev_val.upper()}] {s.signal_type}**: "
            f"{s.entity_name} — {s.description}  \n"
            f"  `{s.signal_id}` (use onto_explain for evidence)"
        )

    lines.append(
        "\nThese signals are pre-computed from the data. Reference them by name "
        "in your response. Use `onto_explain` with the signal_id for the full "
        "evidence chain."
    )
    return "\n".join(lines)


def extract_signal_references(text: str, domain: Any) -> list[str]:
    """Find signal names mentioned in the agent's output."""
    if domain is None or not hasattr(domain, "all_signal_names"):
        return []
    found = []
    for name in domain.all_signal_names():
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            found.append(name)
    return found
