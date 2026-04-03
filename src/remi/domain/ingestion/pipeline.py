"""ingestion/pipeline.py — full document ingestion pipeline.

Orchestrates the complete inbound data flow:
  upload → parse → persist → LLM extraction → resolve to domain models →
  snapshot → signal pipeline → embed

LLM extraction is performed by the ontology-driven ``document_ingestion``
pipeline (classify → extract → enrich) via ``IngestionService``.  The
resolver maps LLM rows directly to domain models with no intermediate
event layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from remi.agent.documents.parsers import parse_document
from remi.agent.documents.types import Document, DocumentStore
from remi.agent.graph.stores import KnowledgeStore
from remi.agent.signals.composite import CompositeProducer
from remi.domain.ingestion.embedding import EmbeddingPipeline
from remi.domain.ingestion.service import IngestionService
from remi.domain.portfolio.protocols import PropertyStore
from remi.domain.queries.snapshots import SnapshotService

_log = structlog.get_logger(__name__)

@dataclass
class IngestResult:
    doc: Document
    report_type: str
    entities_extracted: int
    relationships_extracted: int
    ambiguous_rows: int
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_skipped: int = 0
    validation_warnings: list[str] = field(default_factory=list)
    signals_produced: int = 0
    entities_embedded: int = 0
    pipeline_warnings: list[str] = field(default_factory=list)


class DocumentIngestService:
    """Orchestrates document upload → parse → ingest → enrich → reason."""

    def __init__(
        self,
        document_store: DocumentStore,
        ingestion_service: IngestionService,
        knowledge_store: KnowledgeStore,
        property_store: PropertyStore,
        snapshot_service: SnapshotService,
        signal_pipeline: CompositeProducer,
        embedding_pipeline: EmbeddingPipeline,
    ) -> None:
        self._doc_store = document_store
        self._ingestion = ingestion_service
        self._knowledge_store = knowledge_store
        self._property_store = property_store
        self._snapshot_service = snapshot_service
        self._signal_pipeline = signal_pipeline
        self._embedding_pipeline = embedding_pipeline

    async def ingest_upload(
        self,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        manager: str | None = None,
        run_pipelines: bool = True,
    ) -> IngestResult:
        doc = parse_document(filename, content, content_type)

        await self._doc_store.save(doc)

        ingestion_result = await self._ingestion.ingest(doc, manager=manager)

        doc_with_meta = doc.model_copy(
            update={"metadata": {**doc.metadata, "report_type": ingestion_result.report_type}}
        )
        await self._doc_store.save(doc_with_meta)

        signals_produced = 0
        entities_embedded = 0
        pipeline_warnings: list[str] = []

        if run_pipelines:
            try:
                await self._snapshot_service.capture(effective_date=doc_with_meta.effective_date)
                _log.info("performance_snapshot_captured")
            except Exception as exc:
                pipeline_warnings.append(f"snapshot_capture: {exc}")
                _log.warning("snapshot_capture_failed", exc_info=True)

            try:
                pipeline_result = await self._signal_pipeline.run_all()
                signals_produced = pipeline_result.produced
                _log.info(
                    "signal_pipeline_complete",
                    signals_produced=pipeline_result.produced,
                    sources={k: v.produced for k, v in pipeline_result.per_source.items()},
                )
            except Exception as exc:
                pipeline_warnings.append(f"signal_pipeline: {exc}")
                _log.warning("signal_pipeline_failed", exc_info=True)

            try:
                embed_result = await self._embedding_pipeline.run_full()
                entities_embedded = embed_result.embedded
                _log.info(
                    "embedding_pipeline_complete",
                    embedded=embed_result.embedded,
                    by_type=embed_result.by_type,
                )
            except Exception as exc:
                pipeline_warnings.append(f"embedding_pipeline: {exc}")
                _log.warning("embedding_pipeline_failed", exc_info=True)

        validation_warnings = [
            f"row {w.row_index} ({w.row_type}).{w.field}: {w.issue}"
            for w in ingestion_result.validation_warnings
        ] + [
            f"row {w.row_index} ({w.row_type}).{w.field}: {w.issue}"
            for w in ingestion_result.persist_errors
        ]

        return IngestResult(
            doc=doc_with_meta,
            report_type=ingestion_result.report_type,
            entities_extracted=ingestion_result.entities_created,
            relationships_extracted=ingestion_result.relationships_created,
            ambiguous_rows=len(ingestion_result.ambiguous_rows),
            rows_accepted=ingestion_result.rows_accepted,
            rows_rejected=ingestion_result.rows_rejected,
            rows_skipped=ingestion_result.rows_skipped,
            validation_warnings=validation_warnings,
            signals_produced=signals_produced,
            entities_embedded=entities_embedded,
            pipeline_warnings=pipeline_warnings,
        )
