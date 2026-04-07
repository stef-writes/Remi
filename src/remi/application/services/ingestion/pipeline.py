"""Document ingestion orchestrator — LLM-first upload via workflow engine.

Every tabular upload goes through the document_ingestion workflow YAML.
The LLM sees metadata, column headers, and sample rows — then returns a
column_map, entity type, and report type. Python applies that map
deterministically to every row, then persists.

Manager assignment policy:
  upload_manager_id is set ONLY from the user-supplied ``manager`` form
  field. The LLM may extract a manager name from the report title/metadata
  (e.g. "Alex - Delinquency Report"), but that is stored as document
  metadata (report_manager) — never used to reassign properties. Per-row
  manager columns (e.g. Site Manager Name in property directories) are
  handled inside the row-level persisters, not here.

Phases:
  1. Parse     — file bytes to ``DocumentContent``
  2. Dedup     — content-hash duplicate check
  3. Extract   — workflow engine runs document_ingestion extract step
  4. Manager   — ensure PropertyManager exists from user-supplied param
  5. Map       — apply_column_map to all rows
  6. Validate  — check rows have enough data for persisters
  7. Persist   — row-level persistence via IngestionService
  8. Store     — save to ContentStore + PropertyStore
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.agent.documents import ContentStore
from remi.agent.documents.parsers import parse_document
from remi.agent.documents.types import DocumentKind
from remi.agent.workflow import load_workflow
from remi.application.core.models import (
    Document,
    DocumentType,
    PropertyManager,
    ReportType,
)
from remi.application.infra.graph.schema import entity_schemas_for_prompt
from remi.application.services.ingestion.base import (
    IngestionResult,
    ReviewItem,
    RowWarning,
)
from remi.application.services.ingestion.mapper import apply_column_map
from remi.application.services.ingestion.service import IngestionService
from remi.application.services.ingestion.validation import validate_rows
from remi.types.identity import manager_id as _manager_id

_log = structlog.get_logger(__name__)


@dataclass
class UploadResult:
    """Result of the full upload pipeline, consumed by the API and tool layers."""

    doc: Document
    report_type: str = "unknown"
    entities_extracted: int = 0
    relationships_extracted: int = 0
    ambiguous_rows: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_skipped: int = 0
    observations_captured: int = 0
    validation_warnings: list[RowWarning] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)
    pipeline_warnings: list[str] = field(default_factory=list)
    duplicate_of: Document | None = None


class DocumentIngestService:
    """Top-level orchestrator for document uploads.

    ``_ingestion`` is exposed for the ``correct_row`` API endpoint.
    """

    def __init__(
        self,
        content_store: ContentStore,
        ingestion_service: IngestionService,
        metadata_skip_patterns: tuple[str, ...] = (),
    ) -> None:
        self._content_store = content_store
        self._ingestion = ingestion_service
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
    ) -> UploadResult:
        """Run the full ingestion workflow."""

        # -- Phase 1: Parse -------------------------------------------------------
        doc_content = parse_document(
            filename,
            content,
            content_type,
            extra_skip_patterns=self._skip_patterns,
        )
        doc_content.size_bytes = len(content)

        # -- Phase 2: Dedup -------------------------------------------------------
        content_hash = _content_hash(content)

        existing_doc = await self._ingestion._ps.find_by_content_hash(content_hash)
        if existing_doc is not None:
            doc_model = _build_document_model(
                doc_content,
                content_hash=content_hash,
                document_type=document_type,
                unit_id=unit_id,
                property_id=property_id,
                lease_id=lease_id,
            )
            return UploadResult(
                doc=doc_model,
                duplicate_of=existing_doc,
                report_type=existing_doc.report_type.value,
            )

        # -- Non-tabular: store and return -----------------------------------------
        if doc_content.kind != DocumentKind.tabular:
            await self._content_store.save(doc_content)
            doc_model = _build_document_model(
                doc_content,
                content_hash=content_hash,
                document_type=document_type,
                unit_id=unit_id,
                property_id=property_id,
                lease_id=lease_id,
            )
            await self._ingestion._ps.upsert_document(doc_model)
            return UploadResult(doc=doc_model, report_type="unknown")

        # -- Phase 3: LLM Extract -------------------------------------------------
        columns = doc_content.column_names
        rows = doc_content.rows
        warnings: list[str] = []

        if not columns or not rows:
            warnings.append("No columns or rows found in document")
            await self._content_store.save(doc_content)
            doc_model = _build_document_model(
                doc_content,
                content_hash=content_hash,
                document_type=document_type,
                unit_id=unit_id,
                property_id=property_id,
                lease_id=lease_id,
            )
            await self._ingestion._ps.upsert_document(doc_model)
            return UploadResult(doc=doc_model, pipeline_warnings=warnings)

        extract = await self._llm_extract(doc_content)

        column_map: dict[str, str] = extract.get("column_map", {})
        entity_type: str = extract.get("primary_entity_type", "")
        report_type_str: str = extract.get("report_type", "unknown")
        section_header: str | None = extract.get("section_header_column")
        llm_manager: str | None = extract.get("manager")

        if not column_map or not entity_type:
            _log.warning(
                "llm_extract_empty",
                column_map_keys=list(column_map.keys()),
                entity_type=entity_type,
            )
            warnings.append("LLM returned empty column_map or entity_type")

        # upload_manager_id comes ONLY from the user's explicit choice.
        # The LLM-extracted manager is metadata (who ran the report),
        # not an assignment directive.
        effective_manager_id: str | None = None
        if manager:
            effective_manager_id = await self._ensure_manager(manager)

        _log.info(
            "llm_extract_done",
            report_type=report_type_str,
            entity_type=entity_type,
            llm_manager=llm_manager,
            upload_manager=manager,
            upload_manager_id=effective_manager_id,
            mapped_columns=len(column_map),
            total_rows=len(rows),
        )

        # -- Phase 4: Map ---------------------------------------------------------
        mapped_rows = (
            apply_column_map(
                rows,
                column_map,
                entity_type,
                section_header_column=section_header,
            )
            if column_map and entity_type
            else []
        )

        rt = _resolve_report_type(report_type_str)

        # -- Phase 5: Validate ----------------------------------------------------
        pre_result = IngestionResult(document_id=doc_content.id, report_type=rt)
        validated_rows = validate_rows(mapped_rows, pre_result)

        # -- Phase 6: Persist ------------------------------------------------------
        persist_result = await self._ingestion.ingest_mapped_rows(
            doc_content,
            report_type=rt,
            rows=validated_rows,
            manager=manager,
        )

        persist_result.rows_rejected += pre_result.rows_rejected
        persist_result.rows_skipped += pre_result.rows_skipped
        persist_result.validation_warnings.extend(pre_result.validation_warnings)
        persist_result.observation_rows.extend(pre_result.observation_rows)

        # -- Phase 7: Store --------------------------------------------------------
        await self._content_store.save(doc_content)
        doc_model = _build_document_model(
            doc_content,
            content_hash=content_hash,
            report_type=rt,
            document_type=document_type,
            unit_id=unit_id,
            property_id=property_id,
            lease_id=lease_id,
            manager_id=effective_manager_id,
            report_manager=llm_manager,
        )
        await self._ingestion._ps.upsert_document(doc_model)

        return UploadResult(
            doc=doc_model,
            report_type=rt.value,
            entities_extracted=persist_result.entities_created,
            relationships_extracted=persist_result.relationships_created,
            ambiguous_rows=len(persist_result.ambiguous_rows),
            rows_accepted=persist_result.rows_accepted,
            rows_rejected=persist_result.rows_rejected,
            rows_skipped=persist_result.rows_skipped,
            observations_captured=persist_result.observations_captured,
            validation_warnings=persist_result.validation_warnings,
            review_items=persist_result.review_items,
            pipeline_warnings=warnings,
        )

    async def _ensure_manager(self, manager_name: str) -> str:
        """Create the PropertyManager entity if it doesn't already exist.

        Returns the manager_id.
        """
        from remi.application.core.rules import manager_name_from_tag

        display_name = manager_name_from_tag(manager_name)
        mid = _manager_id(display_name)

        existing = await self._ingestion._ps.get_manager(mid)
        if existing is None:
            mgr = PropertyManager(id=mid, name=display_name)
            await self._ingestion._ps.upsert_manager(mgr)
            _log.info("manager_auto_created", manager_id=mid, name=display_name)

        return mid

    async def _llm_extract(self, content: Any) -> dict[str, Any]:
        """Run the document_ingestion workflow extract step.

        Sends metadata + column headers + sample rows to the LLM.
        Returns the parsed JSON response dict.
        """
        metadata = content.metadata or {}
        sample_rows = content.rows[:5]

        workflow_input = json.dumps(
            {
                "metadata": metadata,
                "column_names": content.column_names,
                "sample_rows": sample_rows,
            },
            default=str,
        )

        context = {"entity_schemas": entity_schemas_for_prompt()}

        try:
            workflow_def = load_workflow("document_ingestion")
            result = await self._ingestion._workflow_runner.run(
                workflow_def,
                workflow_input,
                context=context,
                skip_steps={"capture"},
            )
        except Exception:
            _log.warning("llm_workflow_failed", exc_info=True)
            return {}

        extract_value = result.step("extract")
        if isinstance(extract_value, dict):
            return extract_value
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _resolve_report_type(raw: str) -> ReportType:
    try:
        return ReportType(raw)
    except ValueError:
        return ReportType.UNKNOWN


def _build_document_model(
    content: Any,
    *,
    content_hash: str,
    report_type: ReportType = ReportType.UNKNOWN,
    document_type: str | None = None,
    unit_id: str | None = None,
    property_id: str | None = None,
    lease_id: str | None = None,
    manager_id: str | None = None,
    report_manager: str | None = None,
) -> Document:
    dt = DocumentType.REPORT
    if document_type:
        try:
            dt = DocumentType(document_type)
        except ValueError:
            dt = DocumentType.OTHER

    return Document(
        id=content.id,
        filename=content.filename,
        content_type=content.content_type,
        content_hash=content_hash,
        document_type=dt,
        kind=content.kind.value if hasattr(content.kind, "value") else str(content.kind),
        page_count=content.page_count,
        chunk_count=len(content.chunks),
        row_count=content.row_count,
        size_bytes=content.size_bytes,
        tags=content.tags,
        report_type=report_type,
        unit_id=unit_id,
        property_id=property_id,
        lease_id=lease_id,
        manager_id=manager_id,
        report_manager=report_manager,
    )
