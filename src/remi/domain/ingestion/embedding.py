"""EmbeddingPipeline — generates vectors for domain entities and document rows.

Calls entity-specific extraction functions (in ``extraction.py``) to
produce EmbeddingRequests, batches them through the Embedder, and
upserts the resulting vectors into the VectorStore.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from remi.agent.documents.types import DocumentStore
from remi.agent.signals import SignalStore
from remi.agent.vectors.types import Embedder, EmbeddingRecord, EmbeddingRequest, VectorStore
from remi.domain.ingestion.extraction import (
    extract_maintenance,
    extract_properties,
    extract_tenants,
    extract_units,
)
from remi.domain.ingestion.extraction_sources import extract_document_rows, extract_managers
from remi.domain.portfolio.protocols import PropertyStore

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
        vector_store: VectorStore,
        embedder: Embedder,
        document_store: DocumentStore | None = None,
        signal_store: SignalStore | None = None,
    ) -> None:
        self._ps = property_store
        self._vs = vector_store
        self._embedder = embedder
        self._ds = document_store
        self._ss = signal_store

    async def run_full(self) -> PipelineResult:
        """Re-embed all entities and document rows.

        Upserts by stable IDs; does not clear orphans.
        """
        result = PipelineResult()
        requests = await self._extract_all()

        if not requests:
            _log.info("embedding_pipeline_empty")
            return result

        batch_size = 100
        for i in range(0, len(requests), batch_size):
            batch = requests[i : i + batch_size]
            try:
                vectors = await self._embedder.embed([r.text for r in batch])
            except Exception:
                _log.warning("embedding_batch_failed", batch_start=i, exc_info=True)
                result.errors += len(batch)
                continue

            records = []
            for req, vec in zip(batch, vectors, strict=False):
                records.append(
                    EmbeddingRecord(
                        id=req.id,
                        text=req.text,
                        vector=vec,
                        source_entity_id=req.source_entity_id,
                        source_entity_type=req.source_entity_type,
                        source_field=req.source_field,
                        metadata=req.metadata,
                    )
                )

            await self._vs.put_many(records)
            result.embedded += len(records)
            for rec in records:
                result.by_type[rec.source_entity_type] = (
                    result.by_type.get(rec.source_entity_type, 0) + 1
                )

        _log.info(
            "embedding_pipeline_complete",
            embedded=result.embedded,
            skipped=result.skipped,
            errors=result.errors,
        )
        return result

    async def _extract_all(self) -> list[EmbeddingRequest]:
        requests: list[EmbeddingRequest] = []
        requests.extend(await extract_managers(self._ps, self._ss))
        requests.extend(await extract_tenants(self._ps))
        requests.extend(await extract_units(self._ps))
        requests.extend(await extract_maintenance(self._ps))
        requests.extend(await extract_properties(self._ps))
        if self._ds is not None:
            requests.extend(await extract_document_rows(self._ds))
        return requests
