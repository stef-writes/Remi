"""ingestion/pipeline.py — full document ingestion pipeline.

Orchestrates the complete inbound data flow:
  upload → parse → extract → persist → embed

For non-tabular documents (PDF, DOCX, TXT, images), the pipeline skips
entity extraction and only runs save + embedding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.agent.documents import ContentStore, DocumentContent, parse_document
from remi.application.core.models import Document
from remi.application.services.embedding.pipeline import EmbeddingPipeline
from remi.application.services.ingestion.base import ReviewItem
from remi.application.services.ingestion.rules import extract_rows
from remi.application.services.ingestion.service import IngestionService

_log = structlog.get_logger(__name__)

_PROPERTY_GROUPS_RE = re.compile(
    r"^(.+?)(?:\s+(?:Mgmt|Management|Properties|Portfolio))?$", re.I,
)


def _manager_from_metadata(meta: dict[str, Any]) -> str | None:
    """Extract a manager name from parsed report metadata.

    AppFolio reports include a ``Property Groups:`` header line like
    ``Property Groups: Ryan Steen Mgmt``.  The parser stores this as
    ``meta["property_groups"]``.
    """
    raw = meta.get("property_groups") or ""
    if not raw:
        return None
    m = _PROPERTY_GROUPS_RE.match(raw.strip())
    return m.group(1).strip() if m else raw.strip()


@dataclass
class IngestResult:
    doc: Document
    content: DocumentContent
    report_type: str
    entities_extracted: int
    relationships_extracted: int
    ambiguous_rows: int
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_skipped: int = 0
    validation_warnings: list[str] = field(default_factory=list)
    entities_embedded: int = 0
    pipeline_warnings: list[str] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)


class DocumentIngestService:
    """Orchestrates document upload → parse → ingest → enrich → reason."""

    def __init__(
        self,
        content_store: ContentStore,
        ingestion_service: IngestionService,
        embedding_pipeline: EmbeddingPipeline,
        metadata_skip_patterns: tuple[str, ...] = (),
    ) -> None:
        self._content_store = content_store
        self._ingestion = ingestion_service
        self._embedding_pipeline = embedding_pipeline
        self._skip_patterns = metadata_skip_patterns

    async def ingest_upload(
        self,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        manager: str | None = None,
        unit_id: str | None = None,
        property_id: str | None = None,
        lease_id: str | None = None,
        document_type: str | None = None,
        run_pipelines: bool = True,
    ) -> IngestResult:
        parsed = parse_document(
            filename, content, content_type,
            extra_skip_patterns=self._skip_patterns,
        )

        await self._content_store.save(parsed)

        if parsed.kind.value != "tabular":
            return await self._reference_path(
                parsed,
                manager_id=manager,
                unit_id=unit_id,
                property_id=property_id,
                lease_id=lease_id,
                document_type=document_type,
                run_pipelines=run_pipelines,
            )

        result = await self._rules_path(parsed, manager=manager)
        if result is None:
            result = await self._llm_path(parsed, manager=manager)

        doc_entity = await self._build_document_entity(
            parsed, result.report_type,
            manager_id=manager,
            unit_id=unit_id,
            property_id=property_id,
            lease_id=lease_id,
            document_type=document_type,
        )
        result.doc = doc_entity

        if run_pipelines:
            await self._run_downstream_pipelines(result)

        return result

    async def _reference_path(
        self,
        content: DocumentContent,
        *,
        manager_id: str | None = None,
        unit_id: str | None = None,
        property_id: str | None = None,
        lease_id: str | None = None,
        document_type: str | None = None,
        run_pipelines: bool = True,
    ) -> IngestResult:
        """Handle text/image documents — skip entity extraction, embed only."""
        doc_entity = await self._build_document_entity(
            content, content.kind.value,
            manager_id=manager_id,
            unit_id=unit_id,
            property_id=property_id,
            lease_id=lease_id,
            document_type=document_type,
        )
        result = IngestResult(
            doc=doc_entity,
            content=content,
            report_type=content.kind.value,
            entities_extracted=0,
            relationships_extracted=0,
            ambiguous_rows=0,
        )

        if run_pipelines:
            try:
                embed_result = await self._embedding_pipeline.run_for_document(content.id)
                result.entities_embedded = embed_result.embedded
                _log.info(
                    "reference_doc_embedded",
                    filename=content.filename,
                    kind=content.kind.value,
                    embedded=embed_result.embedded,
                )
            except Exception as exc:
                result.pipeline_warnings.append(f"embedding_pipeline: {exc}")
                _log.warning("reference_doc_embed_failed", exc_info=True)

        return result

    async def _rules_path(
        self,
        content: DocumentContent,
        *,
        manager: str | None = None,
    ) -> IngestResult | None:
        """Try deterministic column-mapping extraction — zero LLM calls."""
        match = extract_rows(content.column_names, content.rows)
        if match is None:
            return None

        report_type, mapped_rows = match

        if not manager:
            manager = _manager_from_metadata(content.metadata)

        _log.info(
            "rules_path_matched",
            filename=content.filename,
            report_type=report_type,
            rows=len(mapped_rows),
            manager_from_metadata=manager,
        )

        ingestion_result = await self._ingestion.ingest_mapped_rows(
            content,
            report_type=report_type,
            rows=mapped_rows,
            manager=manager,
        )

        validation_warnings = [
            f"row {w.row_index} ({w.row_type}).{w.field}: {w.issue}"
            for w in ingestion_result.validation_warnings
        ] + [
            f"row {w.row_index} ({w.row_type}).{w.field}: {w.issue}"
            for w in ingestion_result.persist_errors
        ]

        # Placeholder doc — will be replaced by the caller with the real entity
        placeholder = Document(
            id=content.id,
            filename=content.filename,
            content_type=content.content_type,
            report_type=report_type,
        )

        return IngestResult(
            doc=placeholder,
            content=content,
            report_type=report_type,
            entities_extracted=ingestion_result.entities_created,
            relationships_extracted=ingestion_result.relationships_created,
            ambiguous_rows=len(ingestion_result.ambiguous_rows),
            rows_accepted=ingestion_result.rows_accepted,
            rows_rejected=ingestion_result.rows_rejected,
            rows_skipped=ingestion_result.rows_skipped,
            validation_warnings=validation_warnings,
            review_items=list(ingestion_result.review_items),
        )

    async def _llm_path(
        self,
        content: DocumentContent,
        *,
        manager: str | None = None,
    ) -> IngestResult:
        """Run the LLM extraction pipeline."""
        ingestion_result = await self._ingestion.ingest(content, manager=manager)

        validation_warnings = [
            f"row {w.row_index} ({w.row_type}).{w.field}: {w.issue}"
            for w in ingestion_result.validation_warnings
        ] + [
            f"row {w.row_index} ({w.row_type}).{w.field}: {w.issue}"
            for w in ingestion_result.persist_errors
        ]

        placeholder = Document(
            id=content.id,
            filename=content.filename,
            content_type=content.content_type,
            report_type=ingestion_result.report_type,
        )

        return IngestResult(
            doc=placeholder,
            content=content,
            report_type=ingestion_result.report_type,
            entities_extracted=ingestion_result.entities_created,
            relationships_extracted=ingestion_result.relationships_created,
            ambiguous_rows=len(ingestion_result.ambiguous_rows),
            rows_accepted=ingestion_result.rows_accepted,
            rows_rejected=ingestion_result.rows_rejected,
            rows_skipped=ingestion_result.rows_skipped,
            validation_warnings=validation_warnings,
            review_items=list(ingestion_result.review_items),
        )

    async def _build_document_entity(
        self,
        content: DocumentContent,
        report_type: str,
        *,
        manager_id: str | None = None,
        unit_id: str | None = None,
        property_id: str | None = None,
        lease_id: str | None = None,
        document_type: str | None = None,
    ) -> Document:
        """Create and persist the promoted Document domain model."""
        from remi.application.core.models import DocumentType

        try:
            doc_type = DocumentType(document_type) if document_type else DocumentType.OTHER
        except ValueError:
            doc_type = DocumentType.OTHER

        doc = Document(
            id=content.id,
            filename=content.filename,
            content_type=content.content_type,
            document_type=doc_type,
            kind=content.kind.value,
            row_count=content.row_count,
            chunk_count=len(content.chunks),
            page_count=content.page_count,
            size_bytes=content.size_bytes,
            tags=list(content.tags),
            report_type=report_type,
            manager_id=manager_id,
            unit_id=unit_id,
            property_id=property_id,
            lease_id=lease_id,
        )
        await self._ingestion._ps.upsert_document(doc)
        return doc

    async def _run_downstream_pipelines(self, result: IngestResult) -> None:
        try:
            embed_result = await self._embedding_pipeline.run_for_document(result.content.id)
            result.entities_embedded = embed_result.embedded
            _log.info(
                "embedding_pipeline_complete",
                document_id=result.content.id,
                embedded=embed_result.embedded,
                by_type=embed_result.by_type,
            )
        except Exception as exc:
            result.pipeline_warnings.append(f"embedding_pipeline: {exc}")
            _log.warning("embedding_pipeline_failed", exc_info=True)
