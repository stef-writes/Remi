"""IngestionService — pipeline-driven entity extraction from uploaded documents.

All documents go through the ``document_ingestion`` pipeline
(classify -> extract -> enrich).  The pipeline calls LLMProvider directly
-- no chat runtime, no sandbox session overhead.

The resolver maps LLM-extracted rows directly to domain models and persists
them to PropertyStore and KnowledgeStore in one pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.agent.documents import DocumentContent
from remi.agent.pipeline import IngestionPipelineRunner
from remi.application.core.models import Document, DocumentType
from remi.application.core.protocols import (
    KBEntity,
    KBRelationship,
    KnowledgeWriter,
    PropertyStore,
)
from remi.application.infra.ontology.schema import entity_schemas_for_prompt
from remi.application.services.ingestion.base import (
    IngestionResult,
    ReviewItem,
    ReviewKind,
    ReviewOption,
    ReviewSeverity,
)
from remi.application.services.ingestion.managers import ManagerResolver
from remi.application.services.ingestion.persist import resolve_and_persist
from remi.application.services.ingestion.resolver import PERSISTABLE_TYPES
from remi.application.services.ingestion.validation import validate_rows

logger = structlog.get_logger(__name__)

_PIPELINE = "document_ingestion"

_REPORT_TYPE_TO_DOC_TYPE: dict[str, DocumentType] = {
    "rent_roll": DocumentType.REPORT,
    "delinquency": DocumentType.REPORT,
    "lease_expiration": DocumentType.REPORT,
    "property_directory": DocumentType.REPORT,
}


# ---------------------------------------------------------------------------
# Typed models for LLM pipeline output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrichedRelationship:
    source_id: str
    target_id: str
    relation_type: str


@dataclass(frozen=True)
class EnrichedRow:
    row_index: int
    entity_type: str
    entity_id: str
    properties: dict[str, str | int | float | bool | None]
    relationships: list[EnrichedRelationship] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: object) -> EnrichedRow | None:
        if not isinstance(raw, dict):
            return None
        eid = str(raw.get("entity_id", "")).strip()
        etype = str(raw.get("entity_type", "")).strip()
        if not eid or not etype:
            return None
        rels: list[EnrichedRelationship] = []
        for r in raw.get("relationships", []) or []:
            if not isinstance(r, dict):
                continue
            src = str(r.get("source_id", "")).strip()
            tgt = str(r.get("target_id", "")).strip()
            rtype = str(r.get("relation_type", "")).strip()
            if src and tgt and rtype:
                rels.append(EnrichedRelationship(src, tgt, rtype))
        props_raw = raw.get("properties") or {}
        props: dict[str, str | int | float | bool | None] = {
            str(k): v
            for k, v in props_raw.items()
            if isinstance(v, (str, int, float, bool, type(None)))
        }
        return cls(
            row_index=int(raw.get("row_index", 0)),
            entity_type=etype,
            entity_id=eid,
            properties=props,
            relationships=rels,
        )


@dataclass(frozen=True)
class KnownTypeDescription:
    type: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "description": self.description}


_KNOWN_TYPES: list[KnownTypeDescription] = [
    KnownTypeDescription(
        type="rent_roll",
        description=(
            "Lists every unit in the portfolio with occupancy status, lease dates, "
            "rent, and vacancy days. Has section headers like Current / Vacant-Unrented."
        ),
    ),
    KnownTypeDescription(
        type="delinquency",
        description=(
            "Shows tenants with outstanding balances: amount owed, 0-30 day and 30+ "
            "day buckets, last payment date, tenant status (Current / Notice / Evict)."
        ),
    ),
    KnownTypeDescription(
        type="lease_expiration",
        description=(
            "Details upcoming lease expirations: move-in date, lease-end date, rent "
            "vs market rent, sqft, tenant name. Tags column often carries manager name."
        ),
    ),
    KnownTypeDescription(
        type="property_directory",
        description=(
            "Listing of all properties with assigned property manager and address. "
            "Some properties may have no manager assigned."
        ),
    ),
]


class IngestionService:
    """Extracts entities from documents via the LLM ingestion pipeline
    and persists typed domain models into PropertyStore."""

    def __init__(
        self,
        knowledge_writer: KnowledgeWriter,
        property_store: PropertyStore,
        pipeline_runner: IngestionPipelineRunner,
    ) -> None:
        self._kb = knowledge_writer
        self._ps = property_store
        self._runner = pipeline_runner
        self._manager_resolver = ManagerResolver(
            manager_repo=property_store,
            portfolio_repo=property_store,
        )

    async def ingest_mapped_rows(
        self,
        content: DocumentContent,
        *,
        report_type: str,
        rows: list[dict[str, Any]],
        manager: str | None = None,
    ) -> IngestionResult:
        """Persist pre-mapped rows without calling the LLM pipeline.

        Used by the rule-based extraction path where column mapping has
        already been done deterministically.
        """
        namespace = "ontology"
        result = IngestionResult(document_id=content.id)
        result.report_type = report_type

        upload_portfolio_id: str | None = None
        if manager:
            resolution = await self._manager_resolver.ensure_manager(manager)
            upload_portfolio_id = resolution.portfolio_id
            if resolution.created_new:
                result.review_items.append(
                    ReviewItem(
                        kind=ReviewKind.MANAGER_INFERRED,
                        severity=ReviewSeverity.INFO,
                        message=(
                            f"Created new manager '{resolution.manager_name}' "
                            f"from upload parameter"
                        ),
                        entity_type="PropertyManager",
                        entity_id=resolution.manager_id,
                    )
                )

        validated = validate_rows(rows, result)
        if validated:
            await resolve_and_persist(
                validated,
                report_type=report_type,
                platform="appfolio",
                doc_id=content.id,
                namespace=namespace,
                kb=self._kb,
                ps=self._ps,
                manager_resolver=self._manager_resolver,
                result=result,
                upload_portfolio_id=upload_portfolio_id,
            )
        else:
            logger.warning(
                "rules_mapped_rows_empty_after_validation",
                doc_id=content.id,
                report_type=report_type,
            )

        await self._persist_document_entity(content, result)

        logger.info(
            "rules_ingestion_complete",
            doc_id=content.id,
            report_type=report_type,
            entities=result.entities_created,
            relationships=result.relationships_created,
            rows_accepted=result.rows_accepted,
            rows_rejected=result.rows_rejected,
        )
        return result

    async def ingest(
        self,
        content: DocumentContent,
        *,
        manager: str | None = None,
    ) -> IngestionResult:
        namespace = "ontology"
        result = IngestionResult(document_id=content.id)

        upload_portfolio_id: str | None = None
        if manager:
            resolution = await self._manager_resolver.ensure_manager(manager)
            upload_portfolio_id = resolution.portfolio_id
            if resolution.created_new:
                result.review_items.append(
                    ReviewItem(
                        kind=ReviewKind.MANAGER_INFERRED,
                        severity=ReviewSeverity.INFO,
                        message=(
                            f"Created new manager '{resolution.manager_name}' "
                            f"from upload parameter"
                        ),
                        entity_type="PropertyManager",
                        entity_id=resolution.manager_id,
                    )
                )

        pipeline_input = json.dumps(
            {
                "column_names": content.column_names,
                "sample_rows": content.rows[:5],
                "all_rows": content.rows,
                "known_types": [t.to_dict() for t in _KNOWN_TYPES],
            },
            default=str,
        )

        pipeline_ctx = {
            "entity_schemas": entity_schemas_for_prompt(filter_names=PERSISTABLE_TYPES),
        }

        try:
            pipeline_result = await self._runner.run(
                _PIPELINE,
                pipeline_input,
                context=pipeline_ctx,
                skip_steps={"enrich"},
            )
        except Exception:
            logger.exception("ingestion_pipeline_failed", doc_id=content.id)
            await self._persist_document_entity(content, result)
            return result

        extract_output = pipeline_result.step("extract")
        enrich_output = None

        if not isinstance(extract_output, dict):
            logger.warning(
                "extraction_output_not_dict",
                doc_id=content.id,
                output_type=type(extract_output).__name__,
            )
            await self._persist_document_entity(content, result)
            return result

        report_type = str(extract_output.get("report_type") or "unknown")
        platform = str(extract_output.get("platform") or "appfolio")
        raw_rows = extract_output.get("rows") or []
        unknown_rows = extract_output.get("unknown_rows") or []

        if not isinstance(raw_rows, list):
            raw_rows = []
        if not isinstance(unknown_rows, list):
            unknown_rows = []

        rows = [r for r in raw_rows if isinstance(r, dict)]
        result.report_type = report_type

        if report_type == "unknown":
            result.review_items.append(
                ReviewItem(
                    kind=ReviewKind.CLASSIFICATION_UNCERTAIN,
                    severity=ReviewSeverity.ACTION_NEEDED,
                    message=(
                        f"Could not determine report type for '{content.filename}'"
                    ),
                    entity_type="Document",
                    entity_id=content.id,
                    options=[
                        ReviewOption(id="rent_roll", label="Rent Roll"),
                        ReviewOption(id="delinquency", label="Delinquency"),
                        ReviewOption(id="lease_expiration", label="Lease Expiration"),
                        ReviewOption(id="property_directory", label="Property Directory"),
                    ],
                )
            )

        rows = validate_rows(rows, result)

        if rows:
            await resolve_and_persist(
                rows,
                report_type=report_type,
                platform=platform,
                doc_id=content.id,
                namespace=namespace,
                kb=self._kb,
                ps=self._ps,
                manager_resolver=self._manager_resolver,
                result=result,
                upload_portfolio_id=upload_portfolio_id,
            )
        else:
            logger.warning(
                "extraction_produced_no_rows",
                doc_id=content.id,
                filename=content.filename,
                report_type=report_type,
            )

        if unknown_rows:
            try:
                enrich_result = await self._runner.run(
                    _PIPELINE,
                    pipeline_input,
                    context=pipeline_ctx,
                    skip_steps={"classify", "extract"},
                )
                enrich_output = enrich_result.step("enrich")
                pipeline_result.total_usage = (
                    pipeline_result.total_usage + enrich_result.total_usage
                )
            except Exception:
                logger.warning(
                    "enrich_pipeline_failed", doc_id=content.id, exc_info=True,
                )
                enrich_output = None

        if unknown_rows and isinstance(enrich_output, dict):
            raw_enriched = enrich_output.get("enriched_rows") or []
            if isinstance(raw_enriched, list):
                enriched = [EnrichedRow.from_raw(r) for r in raw_enriched]
                await self._apply_enriched_rows(
                    [e for e in enriched if e is not None], namespace, result,
                    doc_id=content.id,
                )

        await self._persist_document_entity(content, result)

        logger.info(
            "ingestion_complete",
            doc_id=content.id,
            report_type=result.report_type,
            entities=result.entities_created,
            relationships=result.relationships_created,
            prompt_tokens=pipeline_result.total_usage.prompt_tokens,
            completion_tokens=pipeline_result.total_usage.completion_tokens,
        )
        return result

    async def _apply_enriched_rows(
        self,
        enriched: list[EnrichedRow],
        namespace: str,
        result: IngestionResult,
        doc_id: str,
    ) -> None:
        for row in enriched:
            if row.entity_type == "noise":
                continue
            await self._kb.put_entity(
                KBEntity(
                    entity_id=row.entity_id,
                    entity_type=row.entity_type,
                    namespace=namespace,
                    properties={**row.properties, "document_id": doc_id},
                    metadata={"source": "llm_enrichment"},
                )
            )
            result.entities_created += 1
            for rel in row.relationships:
                await self._kb.put_relationship(
                    KBRelationship(
                        source_id=rel.source_id,
                        target_id=rel.target_id,
                        relation_type=rel.relation_type,
                        namespace=namespace,
                    )
                )
                result.relationships_created += 1

    async def _persist_document_entity(
        self,
        content: DocumentContent,
        result: IngestionResult,
        *,
        manager_id: str | None = None,
        property_id: str | None = None,
        unit_id: str | None = None,
        lease_id: str | None = None,
    ) -> None:
        """Upsert the promoted Document domain model via PropertyStore.

        FK projection on the ProjectingPropertyStore auto-materializes
        graph edges (SCOPED_TO, FILED_UNDER, EVIDENCES, MANAGED_BY).
        """
        doc_type = _REPORT_TYPE_TO_DOC_TYPE.get(
            result.report_type, DocumentType.OTHER,
        )
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
            report_type=result.report_type,
            manager_id=manager_id,
            property_id=property_id,
            unit_id=unit_id,
            lease_id=lease_id,
        )
        await self._ps.upsert_document(doc)
