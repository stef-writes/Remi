"""ContextBuilder — assembles the agent's per-turn perception of the world.

The domain schema is injected once at agent priming time via
``build_initial_thread``.  The ContextBuilder handles the per-turn
perception: graph neighborhood and document retrieval.

It produces a typed ``ContextFrame`` whose fields stay structured until
``inject_into_thread`` projects them into prose system messages.
"""

from __future__ import annotations

import asyncio

import structlog

from remi.agent.context.enricher import EntityViewEnricher
from remi.agent.context.frame import ContextFrame, WorldState
from remi.agent.context.rendering import render_graph_context
from remi.agent.graph.retrieval.retriever import GraphRetriever
from remi.agent.graph.stores import WorldModel
from remi.agent.observe.events import Event
from remi.agent.observe.types import SpanKind, Tracer
from remi.agent.signals import DomainSchema
from remi.agent.types import Message
from remi.agent.vectors.types import Embedder, VectorStore
from remi.types.text import estimate_tokens, truncate_to_tokens

_log = structlog.get_logger(__name__)

_DEFAULT_TOKEN_BUDGET = 16_000


class ContextBuilder:
    """Assembles a per-turn ContextFrame from graph and document data.

    The domain schema is **not** injected here — it is part of the
    agent's priming (see ``build_initial_thread``).  The builder
    focuses on per-turn perception:

    1. Optionally resolve question-relevant entities via ``GraphRetriever``
    2. Optionally fetch relevant document chunks via vector search
    """

    def __init__(
        self,
        domain: DomainSchema,
        graph_retriever: GraphRetriever | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        token_budget: int = _DEFAULT_TOKEN_BUDGET,
        empty_state_label: str = "monitored entities",
        enricher: EntityViewEnricher | None = None,
    ) -> None:
        self._domain = domain
        self._graph_retriever = graph_retriever
        self._embedder = embedder
        self._vector_store = vector_store
        self._token_budget = token_budget
        self._empty_state_label = empty_state_label
        self._enricher = enricher

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
        ``"graph"``, ``"documents"``, ``"memory"``.
        ``"domain"`` is accepted but ignored (schema is primed, not per-turn).
        When ``None``, all phases run.
        """
        frame = ContextFrame()
        frame.question = question
        if world is not None:
            frame.world = world

        run_all = phases is None
        needs_graph = run_all or (phases is not None and "graph" in phases)
        needs_documents = run_all or (phases is not None and "documents" in phases)

        async def _fetch_graph() -> None:
            if not (needs_graph and self._graph_retriever is not None and question):
                return
            try:
                retrieval = await self._graph_retriever.retrieve(question)
                frame.entities = retrieval.entities
                frame.neighborhood = retrieval.neighborhood
                if tracer is not None:
                    total_links = sum(len(links) for links in frame.neighborhood.values())
                    async with tracer.span(
                        SpanKind.GRAPH,
                        "graph_retrieval",
                        question_length=len(question),
                        entities_resolved=len(frame.entities),
                        neighborhood_links=total_links,
                        entity_types=[e.entity_type for e in frame.entities][:10],
                    ):
                        pass
            except Exception:
                _log.warning(Event.GRAPH_RETRIEVAL_FAILED, exc_info=True)

        async def _fetch_documents() -> None:
            if not (needs_documents and question and self._vector_store and self._embedder):
                return
            try:
                query_vec = await self._embedder.embed_one(question)
                results = await self._vector_store.search(
                    query_vec,
                    limit=5,
                    min_score=0.3,
                    metadata_filter=None,
                )
                doc_types = {"DocumentRow", "DocumentChunk"}
                doc_hits = [r for r in results if r.record.source_entity_type in doc_types]
                if doc_hits:
                    parts = ["Relevant knowledge base passages:"]
                    for hit in doc_hits[:5]:
                        fname = hit.record.metadata.get("filename", "unknown")
                        page = hit.record.metadata.get("page")
                        loc = f" (page {page})" if page is not None else ""
                        snippet = hit.record.text[:400]
                        parts.append(f"- [{fname}{loc}]: {snippet}")
                    frame.document_context = "\n".join(parts)
            except Exception:
                _log.warning("document_context_fetch_failed", exc_info=True)

        async def _fetch_operational() -> None:
            if self._enricher is None or not frame.entities:
                return
            try:
                frame.operational_context = await self._enricher.enrich(frame.entities)
            except Exception:
                _log.warning("operational_context_fetch_failed", exc_info=True)

        # Graph and document retrieval run first; operational enrichment depends
        # on the entities resolved by _fetch_graph, so run sequentially.
        await asyncio.gather(_fetch_graph(), _fetch_documents())
        await _fetch_operational()

        return frame

    def inject_into_thread(
        self,
        thread: list[Message],
        frame: ContextFrame,
    ) -> None:
        """Inject per-turn perception into the thread as system messages.

        The domain schema is already in the thread from priming.  This
        injects only per-turn perception: document context and graph
        context, under the token budget.

        Injection point: immediately *before* the last user message.
        """
        existing_tokens = sum(estimate_tokens(str(m.content)) for m in thread if m.content)
        remaining = self._token_budget - existing_tokens

        insert_idx = _find_tail_inject_point(thread)

        # Operational context — highest priority, injected first so it sits
        # closest to the user message where LLM attention is strongest.
        if frame.operational_context and remaining > 200:
            op_parts = list(frame.operational_context.values())
            op_text = "\n\n".join(op_parts)
            op_budget = min(remaining // 2, 6000)
            op_cost = estimate_tokens(op_text)
            if op_cost <= op_budget:
                thread.insert(insert_idx, Message(role="system", content=op_text))
                remaining -= op_cost
                insert_idx += 1
            else:
                trimmed_op = truncate_to_tokens(op_text, op_budget)
                if trimmed_op:
                    thread.insert(insert_idx, Message(role="system", content=trimmed_op))
                    remaining -= estimate_tokens(trimmed_op)
                    insert_idx += 1

        if frame.document_context and remaining > 200:
            doc_budget = min(remaining // 3, 2000)
            doc_cost = estimate_tokens(frame.document_context)
            if doc_cost <= doc_budget:
                thread.insert(insert_idx, Message(role="system", content=frame.document_context))
                remaining -= doc_cost
                insert_idx += 1
            else:
                trimmed_doc = truncate_to_tokens(frame.document_context, doc_budget)
                if trimmed_doc:
                    thread.insert(insert_idx, Message(role="system", content=trimmed_doc))
                    remaining -= estimate_tokens(trimmed_doc)
                    insert_idx += 1

        if remaining > 200:
            graph_ctx = render_graph_context(frame, max_tokens=remaining)
            if graph_ctx:
                thread.insert(insert_idx, Message(role="system", content=graph_ctx))


def _find_tail_inject_point(thread: list[Message]) -> int:
    """Find the insertion index just before the last user message.

    Places dynamic per-turn context in *recent* context where LLM
    attention is strongest, while keeping the static prefix (system
    prompt + schema) contiguous for KV-cache hits.

    Falls back to after the static system prefix if no user message
    exists yet (e.g. first turn).
    """
    for i in range(len(thread) - 1, -1, -1):
        if thread[i].role == "user":
            return i
    idx = 0
    for i, m in enumerate(thread):
        if m.role == "system":
            idx = i + 1
        else:
            break
    return idx


def build_context_builder(
    *,
    domain: DomainSchema,
    world_model: WorldModel | None = None,
    vector_store: VectorStore | None = None,
    embedder: Embedder | None = None,
    name_fields: tuple[str, ...] | None = None,
    empty_state_label: str = "monitored entities",
    enricher: EntityViewEnricher | None = None,
) -> ContextBuilder:
    """Factory: assembles a ContextBuilder with its GraphRetriever.

    ``world_model`` is the agent's read-only view of whatever domain
    world it operates in.  The kernel never imports application-layer
    types — the ``WorldModel`` ABC lives in ``agent/graph/stores``.
    """
    graph_retriever = GraphRetriever(
        world_model=world_model,
        vector_store=vector_store,
        embedder=embedder,
        name_fields=name_fields,
    )
    return ContextBuilder(
        domain=domain,
        graph_retriever=graph_retriever,
        embedder=embedder,
        vector_store=vector_store,
        empty_state_label=empty_state_label,
        enricher=enricher,
    )
