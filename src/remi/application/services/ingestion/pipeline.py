"""Ingestion host — thin entry point, delegates everything to the YAML workflow.

Responsibilities (things the YAML workflow cannot do):
  1. Parse      — bytes → DocumentContent (parser knows file types)
  2. Dedup      — content-hash check against the store
  3. Guard      — non-tabular / empty early exits
  4. Run        — hand off to the document_ingestion YAML workflow
  5. Save       — persist the Document record after workflow completes

Everything else — manager resolution, report type classification, column
mapping, validation, entity persistence — lives in the YAML workflow and its
registered Python tools (transforms.py).
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
from remi.application.core.models import Document, DocumentType, PropertyManager, ReportType
from remi.application.services.ingestion.base import IngestionResult, ReviewItem, RowWarning  # noqa: F401
from remi.application.services.ingestion.matcher import entity_schemas_for_prompt
from remi.application.services.ingestion.schemas import INGESTION_SCHEMAS
from remi.application.services.ingestion.service import IngestionService
from remi.application.services.ingestion.transforms import register_ingestion_tools
from remi.types.identity import manager_id as _manager_id

_log = structlog.get_logger(__name__)


@dataclass
class UploadResult:
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
    """Thin host — parse/dedup/guard, then hand off to the YAML workflow."""

    def __init__(
        self,
        content_store: ContentStore,
        ingestion_service: IngestionService,
        metadata_skip_patterns: tuple[str, ...] = (),
        section_labels: frozenset[str] = frozenset(),
    ) -> None:
        self._content_store = content_store
        self._ingestion = ingestion_service
        self._skip_patterns = metadata_skip_patterns
        self._section_labels = section_labels

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

        # 1. Parse
        doc_content = parse_document(
            filename, content, content_type,
            extra_skip_patterns=self._skip_patterns,
            section_labels=self._section_labels,
        )
        doc_content.size_bytes = len(content)

        # 2. Dedup
        content_hash = hashlib.sha256(content).hexdigest()
        existing = await self._ingestion._ps.find_by_content_hash(content_hash)
        if existing is not None:
            return UploadResult(
                doc=_build_doc(doc_content, content_hash=content_hash,
                               document_type=document_type, unit_id=unit_id,
                               property_id=property_id, lease_id=lease_id),
                duplicate_of=existing,
                report_type=existing.report_type.value,
            )

        # 3. Guard — non-tabular
        if doc_content.kind != DocumentKind.tabular:
            await self._content_store.save(doc_content)
            doc = _build_doc(doc_content, content_hash=content_hash,
                             document_type=document_type, unit_id=unit_id,
                             property_id=property_id, lease_id=lease_id)
            await self._ingestion._ps.upsert_document(doc)
            return UploadResult(doc=doc, report_type="unknown")

        # 4. Guard — empty
        warnings: list[str] = []
        if not doc_content.column_names or not doc_content.rows:
            warnings.append("No columns or rows found in document")
            await self._content_store.save(doc_content)
            doc = _build_doc(doc_content, content_hash=content_hash,
                             document_type=document_type, unit_id=unit_id,
                             property_id=property_id, lease_id=lease_id)
            await self._ingestion._ps.upsert_document(doc)
            return UploadResult(doc=doc, pipeline_warnings=warnings)

        # 5. Workflow — YAML DAG owns all entity work
        result, extract_data = await self._run_workflow(
            doc_content, doc_content.rows, upload_manager_hint=manager,
        )

        rt = _resolve_rt(extract_data.get("report_type", "unknown"))
        llm_manager = extract_data.get("manager")

        # Document record gets the resolved manager as metadata only
        doc_manager_id: str | None = None
        resolved_name = llm_manager or manager
        if resolved_name:
            doc_manager_id = await self._ensure_manager(resolved_name)

        # 6. Save
        await self._content_store.save(doc_content)
        doc = _build_doc(
            doc_content, content_hash=content_hash, report_type=rt,
            document_type=document_type, unit_id=unit_id,
            property_id=property_id, lease_id=lease_id,
            manager_id=doc_manager_id, report_manager=llm_manager,
        )
        await self._ingestion._ps.upsert_document(doc)

        return UploadResult(
            doc=doc,
            report_type=rt.value,
            entities_extracted=result.entities_created,
            relationships_extracted=result.relationships_created,
            ambiguous_rows=len(result.ambiguous_rows),
            rows_accepted=result.rows_accepted,
            rows_rejected=result.rows_rejected,
            rows_skipped=result.rows_skipped,
            observations_captured=result.observations_captured,
            validation_warnings=result.validation_warnings,
            review_items=result.review_items,
            pipeline_warnings=warnings,
        )

    async def _build_graph_context(self) -> str:
        """Render a compact snapshot of existing managers and properties.

        Passed as ``context.graph_context`` to the capture step so the LLM
        can resolve identities against what's already in the system.
        """
        ps = self._ingestion._ps
        lines: list[str] = []

        managers = await ps.list_managers()
        if managers:
            lines.append("## Managers")
            for m in managers:
                lines.append(f"- id={m.id}  name={m.name}")

        properties = await ps.list_properties()
        if properties:
            lines.append("## Properties")
            for p in properties:
                mgr = f"  manager={p.manager_id}" if p.manager_id else ""
                lines.append(f"- id={p.id}  name={p.name}  address={p.address}{mgr}")

        return "\n".join(lines) if lines else "(empty — no entities ingested yet)"

    async def _run_workflow(
        self,
        content: Any,
        rows: list[dict[str, Any]],
        *,
        upload_manager_hint: str | None = None,
    ) -> tuple[IngestionResult, dict[str, Any]]:
        from remi.application.core.models.enums import ReportType as _RT

        result = IngestionResult(document_id=content.id, report_type=_RT.UNKNOWN)

        # IngestionCtx is created by the initialize tool inside the workflow —
        # the host just passes the raw materials.
        register_ingestion_tools(
            self._ingestion._workflow_runner._tool_registry,
            ps=self._ingestion._ps,
            doc_id=content.id,
            platform=content.metadata.get("platform", "appfolio"),
            result=result,
            all_rows=rows,
            upload_manager_hint=upload_manager_hint,
        )

        graph_context = await self._build_graph_context()

        try:
            wf = load_workflow("document_ingestion")
            wf_result = await self._ingestion._workflow_runner.run(
                wf,
                json.dumps({
                    "metadata": content.metadata or {},
                    "column_names": content.column_names,
                    "sample_rows": content.rows[:5],
                }, default=str),
                context={
                    "entity_schemas": entity_schemas_for_prompt(),
                    "upload_manager_hint": upload_manager_hint or "",
                    # Passed to the inspect step so the LLM sees real values,
                    # not just headers. Capped at 50 rows to keep prompt size sane.
                    "full_rows": json.dumps(content.rows[:50], default=str),
                    # Passed to the capture step so the LLM can resolve identities
                    # against what already exists in the system.
                    "graph_context": graph_context,
                },
                output_schemas=INGESTION_SCHEMAS,
            )
        except Exception:
            _log.warning("ingestion_workflow_failed", exc_info=True)
            return result, {}

        extract_data = wf_result.step("extract")
        if not isinstance(extract_data, dict):
            extract_data = {}

        rt_str = extract_data.get("report_type", "unknown")
        try:
            result.report_type = _RT(rt_str)
        except ValueError:
            result.report_type = _RT.UNKNOWN

        return result, extract_data

    async def _ensure_manager(self, name: str) -> str:
        from remi.application.core.rules import manager_name_from_tag
        display = manager_name_from_tag(name)
        mid = _manager_id(display)
        if await self._ingestion._ps.get_manager(mid) is None:
            await self._ingestion._ps.upsert_manager(PropertyManager(id=mid, name=display))
        return mid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_rt(raw: str) -> ReportType:
    try:
        return ReportType(raw)
    except ValueError:
        return ReportType.UNKNOWN


def _build_doc(
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
