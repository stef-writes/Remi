"""IngestionService — structured entity extraction from uploaded documents.

Report type detection uses a two-tier approach:

  1. Structural (fast): scored column fingerprinting via detect_report_type_scored().
     Returns the best-matching known type when confidence >= threshold.

  2. Semantic (LLM fallback): when structural detection returns UNKNOWN or scores
     below the threshold, the optional report_classifier agent is asked to identify
     the report type from column names and sample rows.  This path is skipped
     gracefully when no LLM API key is configured.

Ingest routing uses a registry dict (_INGEST_HANDLERS) so new report types can
be added by registering a handler function without touching this routing logic.
Anything not in the registry falls back to ingest_generic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from remi.documents.appfolio_schema import (
    AppFolioReportType,
    detect_report_type_scored,
)
from remi.knowledge.ingestion.base import IngestionResult
from remi.knowledge.ingestion.delinquency import ingest_delinquency
from remi.knowledge.ingestion.generic import ingest_generic
from remi.knowledge.ingestion.lease_expiration import ingest_lease_expiration
from remi.knowledge.ingestion.property_directory import ingest_property_directory
from remi.knowledge.ingestion.rent_roll import ingest_rent_roll
from remi.models.documents import Document
from remi.models.memory import Entity, KnowledgeStore
from remi.models.properties import Address, Portfolio, Property, PropertyManager, PropertyStore
from remi.shared.text import manager_name_from_tag, slugify

ClassifyFn = Callable[[Document], Awaitable[str | None]]

# Minimum structural confidence to trust fingerprint detection without LLM.
_STRUCTURAL_CONFIDENCE_THRESHOLD = 0.5

logger = structlog.get_logger(__name__)


class IngestionService:
    """Extracts entities and relationships from documents into a KnowledgeStore
    and upserts typed domain models into PropertyStore."""

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        property_store: PropertyStore,
        classify_fn: ClassifyFn | None = None,
    ) -> None:
        self._kb = knowledge_store
        self._ps = property_store
        self._classify_fn = classify_fn

    async def _ensure_manager(self, manager_tag: str) -> str:
        """Create or retrieve a manager + portfolio for a given tag. Returns portfolio_id."""
        mgr_name = manager_name_from_tag(manager_tag)
        manager_id = slugify(f"manager:{mgr_name}")
        await self._ps.upsert_manager(
            PropertyManager(id=manager_id, name=mgr_name, manager_tag=manager_tag)
        )
        portfolio_id = slugify(f"portfolio:{mgr_name}")
        await self._ps.upsert_portfolio(
            Portfolio(
                id=portfolio_id,
                manager_id=manager_id,
                name=f"{mgr_name} Portfolio",
            )
        )
        return portfolio_id

    async def _upsert_property_safe(
        self,
        prop_id: str,
        name: str,
        addr: Address,
        portfolio_id: str | None = None,
    ) -> None:
        existing = await self._ps.get_property(prop_id)
        if portfolio_id is not None:
            effective_pid = portfolio_id
        elif existing is not None and existing.portfolio_id:
            effective_pid = existing.portfolio_id
        else:
            effective_pid = ""

        await self._ps.upsert_property(
            Property(id=prop_id, portfolio_id=effective_pid, name=name, address=addr)
        )

    async def _upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        namespace: str,
        props: dict[str, Any],
        result: IngestionResult,
    ) -> None:
        existing = await self._kb.get_entity(namespace, entity_id)
        if existing:
            merged = {**existing.properties, **props}
            await self._kb.put_entity(
                Entity(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    namespace=namespace,
                    properties=merged,
                )
            )
        else:
            await self._kb.put_entity(
                Entity(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    namespace=namespace,
                    properties=props,
                )
            )
            result.entities_created += 1

    async def _classify_with_llm(self, doc: Document) -> str | None:
        """Delegate to the injected classify callback, if provided."""
        if self._classify_fn is None:
            return None
        return await self._classify_fn(doc)

    async def ingest(
        self,
        doc: Document,
        *,
        manager: str | None = None,
    ) -> IngestionResult:
        namespace = f"doc:{doc.id}"

        # --- Two-tier report type detection ---
        structural_type, confidence = detect_report_type_scored(doc.column_names)
        is_confident = (
            structural_type != AppFolioReportType.UNKNOWN
            and confidence >= _STRUCTURAL_CONFIDENCE_THRESHOLD
        )

        if is_confident:
            report_type = structural_type
        else:
            llm_type = await self._classify_with_llm(doc)
            report_type = llm_type if llm_type else AppFolioReportType.UNKNOWN
            if llm_type and llm_type != AppFolioReportType.UNKNOWN:
                logger.info(
                    "report_type_from_llm",
                    doc_id=doc.id,
                    structural_type=structural_type,
                    structural_confidence=confidence,
                    llm_type=llm_type,
                )

        result = IngestionResult(document_id=doc.id, report_type=report_type)

        await self._kb.put_entity(
            Entity(
                entity_id=f"document:{doc.id}",
                entity_type="document",
                namespace=namespace,
                properties={
                    "filename": doc.filename,
                    "content_type": doc.content_type,
                    "row_count": doc.row_count,
                    "columns": doc.column_names,
                    "report_type": report_type,
                    "detection_confidence": confidence,
                },
            )
        )
        result.entities_created += 1

        upload_portfolio_id: str | None = None
        if manager:
            upload_portfolio_id = await self._ensure_manager(manager)

        await self._route_ingest(report_type, doc, namespace, result, upload_portfolio_id)

        logger.info(
            "ingestion_complete",
            doc_id=doc.id,
            report_type=report_type,
            detection_confidence=confidence,
            entities=result.entities_created,
            relationships=result.relationships_created,
            ambiguous=len(result.ambiguous_rows),
        )
        return result

    async def _route_ingest(
        self,
        report_type: str,
        doc: Document,
        namespace: str,
        result: IngestionResult,
        upload_portfolio_id: str | None,
    ) -> None:
        """Dispatch to the appropriate ingest handler via registry lookup."""
        # Handlers that only need (doc, namespace, result, kb, ps, upsert_entity,
        # upsert_property_safe, upload_portfolio_id)
        _simple_handlers = {
            AppFolioReportType.RENT_ROLL: ingest_rent_roll,
            AppFolioReportType.DELINQUENCY: ingest_delinquency,
        }
        # Handlers that additionally need ensure_manager
        _manager_aware_handlers = {
            AppFolioReportType.LEASE_EXPIRATION: ingest_lease_expiration,
            AppFolioReportType.PROPERTY_DIRECTORY: ingest_property_directory,
        }

        if report_type in _simple_handlers:
            await _simple_handlers[report_type](
                doc,
                namespace,
                result,
                self._kb,
                self._ps,
                self._upsert_entity,
                self._upsert_property_safe,
                upload_portfolio_id,
            )
        elif report_type in _manager_aware_handlers:
            await _manager_aware_handlers[report_type](
                doc,
                namespace,
                result,
                self._kb,
                self._ps,
                self._upsert_entity,
                self._upsert_property_safe,
                self._ensure_manager,
                upload_portfolio_id,
            )
        else:
            logger.info(
                "ingest_fallback_to_generic",
                doc_id=doc.id,
                report_type=report_type,
            )
            await ingest_generic(doc, namespace, result, self._kb, self._upsert_entity)
