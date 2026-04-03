"""ContextBuilder — assembles the agent's per-turn perception of the world.

The TBox (domain ontology) is injected once at agent priming time via
``build_initial_thread``.  The ContextBuilder handles the per-turn ABox:
active signals, graph neighborhood, and semantic relevance ranking.

It produces a typed ``ContextFrame`` whose ``perception`` field holds
structured situational awareness.  The frame stays typed until
``inject_into_thread`` projects it into prose system messages.
"""

from __future__ import annotations

import asyncio

import structlog

from remi.agent.context.frame import (
    CompoundingSituation,
    ContextFrame,
    PerceptionSnapshot,
    WorldState,
)
from remi.agent.context.rendering import (
    render_active_signals,
    render_graph_context,
)
from remi.agent.graph.retriever import GraphRetriever
from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.observe.events import Event
from remi.agent.observe.types import SpanKind, Tracer
from remi.agent.signals import DomainTBox, MutableTBox, SignalStore
from remi.agent.types import Message
from remi.agent.vectors.types import Embedder, VectorStore
from remi.types.text import estimate_tokens, truncate_to_tokens

_log = structlog.get_logger(__name__)

_DEFAULT_TOKEN_BUDGET = 16_000


class ContextBuilder:
    """Assembles a per-turn ContextFrame from signals and graph data.

    The TBox is **not** injected here — it is part of the agent's priming
    (see ``build_initial_thread``).  The builder focuses on the ABox:

    1. Fetch and rank active signals → typed ``PerceptionSnapshot``
    2. Optionally resolve question-relevant entities via ``GraphRetriever``

    Injection is token-budgeted: the total injected context will not
    exceed ``token_budget`` tokens (approximate, char-based estimate).
    """

    def __init__(
        self,
        domain: DomainTBox | MutableTBox,
        signal_store: SignalStore | None = None,
        graph_retriever: GraphRetriever | None = None,
        embedder: Embedder | None = None,
        token_budget: int = _DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self._domain = domain
        self._signal_store = signal_store
        self._graph_retriever = graph_retriever
        self._embedder = embedder
        self._token_budget = token_budget

    async def build(
        self,
        question: str | None = None,
        *,
        tracer: Tracer | None = None,
        phases: set[str] | None = None,
        world: WorldState | None = None,
    ) -> ContextFrame:
        """Build a context frame, optionally restricted to *phases*.

        *phases* controls which per-turn injection steps run.  Valid values:
        ``"signals"``, ``"graph"``, ``"memory"``.
        ``"domain"`` is accepted but ignored (TBox is primed, not per-turn).
        When ``None``, all phases run.
        """
        frame = ContextFrame()
        frame.question = question
        if world is not None:
            frame.world = world

        run_all = phases is None
        needs_signals = run_all or (phases is not None and "signals" in phases)
        needs_graph = run_all or (phases is not None and "graph" in phases)

        frame.policies = list(getattr(self._domain, "policies", []))
        frame.causal_chains = list(getattr(self._domain, "causal_chains", []))

        async def _fetch_signals() -> None:
            if not (needs_signals and self._signal_store is not None):
                return
            frame.signal_summary = await render_active_signals(
                self._signal_store,
                question=question,
                embedder=self._embedder,
            )
            try:
                frame.signals = await self._signal_store.list_signals()
            except Exception:
                _log.warning("signal_list_fetch_failed", exc_info=True)

            severity_counts: dict[str, int] = {}
            for s in frame.signals:
                sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

            compounding: list[CompoundingSituation] = []
            for s in frame.signals:
                ev = s.evidence or {}
                if "composition_rule" in ev:
                    sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
                    compounding.append(CompoundingSituation(
                        name=s.signal_type,
                        severity=sev,
                        constituents=ev.get("constituent_types", []),
                        entity_ids=ev.get("constituent_ids", []),
                    ))

            frame.perception = PerceptionSnapshot(
                active_signals=len(frame.signals),
                severity_counts=severity_counts,
                compounding=compounding,
            )

            if tracer is not None:
                async with tracer.span(
                    SpanKind.PERCEPTION,
                    "signal_perception",
                    active_signals=len(frame.signals),
                    severity_breakdown=frame.perception.severity_breakdown,
                    compounding_count=len(compounding),
                    signal_types=[s.signal_type for s in frame.signals][:25],
                ):
                    pass

        async def _fetch_graph() -> None:
            if not (needs_graph and self._graph_retriever is not None and question):
                return
            try:
                retrieval = await self._graph_retriever.retrieve(question)
                frame.entities = retrieval.entities
                frame.neighborhood = retrieval.neighborhood
                if retrieval.signals:
                    seen = {s.signal_id for s in frame.signals}
                    for s in retrieval.signals:
                        if s.signal_id not in seen:
                            frame.signals.append(s)
                if tracer is not None:
                    total_links = sum(len(links) for links in frame.neighborhood.values())
                    async with tracer.span(
                        SpanKind.GRAPH,
                        "graph_retrieval",
                        question_length=len(question),
                        entities_resolved=len(frame.entities),
                        neighborhood_links=total_links,
                        entity_types=[e.entity_type for e in frame.entities][:10],
                        signals_attached=len(retrieval.signals),
                    ):
                        pass
            except Exception:
                _log.warning(Event.GRAPH_RETRIEVAL_FAILED, exc_info=True)

        await asyncio.gather(_fetch_signals(), _fetch_graph())

        return frame

    def inject_into_thread(
        self,
        thread: list[Message],
        frame: ContextFrame,
    ) -> None:
        """Inject per-turn perception into the thread as system messages.

        The TBox is already in the thread from priming.  This injects
        only ABox perception: signal summary and graph context, under
        the token budget.
        """
        existing_tokens = sum(estimate_tokens(str(m.content)) for m in thread if m.content)
        remaining = self._token_budget - existing_tokens

        tbox_in_thread = any(
            m.role == "system" and m.content and "Domain Context" in str(m.content)
            for m in thread[1:]
        )
        insert_idx = 2 if tbox_in_thread else 1

        if frame.signal_summary and remaining > 200:
            signal_budget = remaining // 2
            cost = estimate_tokens(frame.signal_summary)
            if cost <= signal_budget:
                thread.insert(insert_idx, Message(role="system", content=frame.signal_summary))
                remaining -= cost
                insert_idx += 1
            else:
                trimmed = truncate_to_tokens(frame.signal_summary, signal_budget)
                if trimmed:
                    thread.insert(insert_idx, Message(role="system", content=trimmed))
                    remaining -= estimate_tokens(trimmed)
                    insert_idx += 1

        if remaining > 200:
            graph_ctx = render_graph_context(frame, max_tokens=remaining)
            if graph_ctx:
                thread.insert(insert_idx, Message(role="system", content=graph_ctx))


def build_context_builder(
    *,
    domain: DomainTBox | MutableTBox,
    signal_store: SignalStore,
    knowledge_graph: KnowledgeGraph,
    vector_store: VectorStore | None = None,
    embedder: Embedder | None = None,
) -> ContextBuilder:
    """Factory: assembles a ContextBuilder with its GraphRetriever."""
    graph_retriever = GraphRetriever(
        knowledge_graph=knowledge_graph,
        vector_store=vector_store,
        embedder=embedder,
        signal_store=signal_store,
    )
    return ContextBuilder(
        domain=domain,
        signal_store=signal_store,
        graph_retriever=graph_retriever,
        embedder=embedder,
    )
