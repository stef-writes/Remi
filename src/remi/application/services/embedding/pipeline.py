"""EmbeddingPipeline — generates vectors for domain entities and document rows.

Calls entity-specific extraction functions (in ``extraction.py``) to
produce EmbeddingRequests, batches them through the Embedder, and
upserts the resulting vectors into the VectorStore.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from remi.agent.documents import ContentStore
from remi.application.core.protocols import (
    EmbedRequest,
    PropertyStore,
    TextIndexer,
)
from remi.application.services.embedding.extraction import (
    extract_maintenance,
    extract_properties,
    extract_tenants,
    extract_units,
)
from remi.application.services.embedding.sources import (
    SignalStoreProtocol,
    extract_document_chunks,
    extract_document_rows,
    extract_managers,
)

_log = structlog.get_logger(__name__)


@dataclass
class PipelineResult:
    embedded: int = 0
    skipped: int = 0
    errors: int = 0
    by_type: dict[str, int] = field(default_factory=dict)


class EmbeddingPipeline:
    """Extracts text from domain entities and document rows, embeds, and stores vectors."""

    def __init__(
        self,
        property_store: PropertyStore,
        text_indexer: TextIndexer,
        content_store: ContentStore | None = None,
        signal_store: SignalStoreProtocol | None = None,
    ) -> None:
        self._ps = property_store
        self._indexer = text_indexer
        self._content_store = content_store
        self._ss = signal_store

    async def run_full(self) -> PipelineResult:
        """Re-embed all entities and document rows.

        Upserts by stable IDs; does not clear orphans.
        """
        return await self._index(await self._extract_all())

    async def run_for_document(self, document_id: str) -> PipelineResult:
        """Embed only the rows/chunks belonging to a specific document.

        Much cheaper than ``run_full`` — call this after a single document
        upload instead of re-embedding the entire corpus.
        """
        if self._content_store is None:
            return PipelineResult()
        requests: list[EmbedRequest] = []
        requests.extend(
            r for r in await extract_document_rows(self._content_store, self._ps)
            if r.source_entity_id == document_id
        )
        requests.extend(
            r for r in await extract_document_chunks(self._content_store, self._ps)
            if r.source_entity_id == document_id
        )
        return await self._index(requests)

    async def _index(self, requests: list[EmbedRequest]) -> PipelineResult:
        result = PipelineResult()
        if not requests:
            _log.info("embedding_pipeline_empty")
            return result

        try:
            indexed = await self._indexer.index_many(requests)
            result.embedded = indexed
            for req in requests[:indexed]:
                result.by_type[req.source_entity_type] = (
                    result.by_type.get(req.source_entity_type, 0) + 1
                )
        except Exception:
            _log.warning("embedding_pipeline_index_failed", exc_info=True)
            result.errors = len(requests)

        _log.info(
            "embedding_pipeline_complete",
            embedded=result.embedded,
            skipped=result.skipped,
            errors=result.errors,
        )
        return result

    async def _extract_all(self) -> list[EmbedRequest]:
        requests: list[EmbedRequest] = []
        requests.extend(await extract_managers(self._ps, self._ss))
        requests.extend(await extract_tenants(self._ps))
        requests.extend(await extract_units(self._ps))
        requests.extend(await extract_maintenance(self._ps))
        requests.extend(await extract_properties(self._ps))
        if self._content_store is not None:
            requests.extend(await extract_document_rows(self._content_store, self._ps))
            requests.extend(await extract_document_chunks(self._content_store, self._ps))
        return requests
