"""DocumentIngestService — upload, parse, ingest, and enrich documents.

Orchestrates the full document ingestion pipeline:
  parse → persist → structured ingest → LLM enrich → snapshot →
  signal pipeline (rule + statistical) → pattern detection → embed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from remi.domain.documents.models import Document, DocumentStore
from remi.domain.memory.ports import KnowledgeStore
from remi.domain.properties.ports import PropertyStore
from remi.infrastructure.documents.parsers import parse_csv, parse_excel
from remi.infrastructure.knowledge.enrichment import enrich_ambiguous_rows
from remi.infrastructure.knowledge.ingestion import IngestionService

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

_log = structlog.get_logger(__name__)

_CSV_TYPES = {"text/csv", "application/csv"}
_EXCEL_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


@dataclass
class IngestResult:
    doc: Document
    report_type: str
    entities_extracted: int
    relationships_extracted: int
    ambiguous_rows: int
    signals_produced: int = 0
    hypotheses_proposed: int = 0
    entities_embedded: int = 0


class DocumentIngestService:
    """Orchestrates document upload → parse → ingest → enrich → reason."""

    def __init__(
        self,
        document_store: DocumentStore,
        ingestion_service: IngestionService,
        knowledge_store: KnowledgeStore,
        property_store: PropertyStore,
        container: Container,
    ) -> None:
        self._doc_store = document_store
        self._ingestion = ingestion_service
        self._knowledge_store = knowledge_store
        self._property_store = property_store
        self._container = container

    async def ingest_upload(
        self,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        manager: str | None = None,
    ) -> IngestResult:
        ct = content_type.lower()
        if ct in _CSV_TYPES or filename.lower().endswith(".csv"):
            doc = parse_csv(filename, content)
        elif ct in _EXCEL_TYPES or filename.lower().endswith((".xlsx", ".xls")):
            doc = parse_excel(filename, content)
        else:
            raise ValueError(
                f"Unsupported file type: {ct}. Supported: CSV, Excel (.xlsx)."
            )

        await self._doc_store.save(doc)

        ingestion_result = await self._ingestion.ingest(doc, manager=manager)

        doc_with_meta = doc.model_copy(
            update={"metadata": {**doc.metadata, "report_type": ingestion_result.report_type}}
        )
        await self._doc_store.save(doc_with_meta)

        enriched_entities, enriched_rels = await enrich_ambiguous_rows(
            ingestion_result.ambiguous_rows,
            doc,
            self._knowledge_store,
            self._container,
        )

        signals_produced = 0
        hypotheses_proposed = 0
        entities_embedded = 0

        # Capture performance snapshot (needed by some entailment evaluators)
        try:
            await self._container.snapshot_service.capture()
            _log.info("performance_snapshot_captured")
        except Exception:
            _log.warning("snapshot_capture_failed", exc_info=True)

        # Run full signal pipeline (rule-based + statistical)
        try:
            pipeline_result = await self._container.signal_pipeline.run_all()
            signals_produced = pipeline_result.produced
            _log.info(
                "signal_pipeline_complete",
                signals_produced=pipeline_result.produced,
                sources={k: v.produced for k, v in pipeline_result.per_source.items()},
            )
        except Exception:
            _log.warning("signal_pipeline_failed", exc_info=True)

        # Run pattern detection to discover new hypotheses from fresh data
        try:
            detector_result = await self._container.pattern_detector.run()
            hypotheses_proposed = detector_result.proposed
            _log.info(
                "pattern_detection_complete",
                hypotheses_proposed=detector_result.proposed,
                types_scanned=detector_result.types_scanned,
            )
        except Exception:
            _log.warning("pattern_detection_failed", exc_info=True)

        # Re-embed entities so semantic search reflects new data
        try:
            embed_result = await self._container.embedding_pipeline.run_full()
            entities_embedded = embed_result.embedded
            _log.info(
                "embedding_pipeline_complete",
                embedded=embed_result.embedded,
                by_type=embed_result.by_type,
            )
        except Exception:
            _log.warning("embedding_pipeline_failed", exc_info=True)

        return IngestResult(
            doc=doc_with_meta,
            report_type=ingestion_result.report_type,
            entities_extracted=ingestion_result.entities_created + enriched_entities,
            relationships_extracted=ingestion_result.relationships_created + enriched_rels,
            ambiguous_rows=len(ingestion_result.ambiguous_rows),
            signals_produced=signals_produced,
            hypotheses_proposed=hypotheses_proposed,
            entities_embedded=entities_embedded,
        )
