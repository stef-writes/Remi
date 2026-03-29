"""EmbeddingPipeline — extracts embeddable text from domain entities and
raw document rows, generates vectors via the Embedder, and stores them in
the VectorStore.

Called after document ingestion to keep the vector index in sync with
the ABox. Each entity type has a text extraction strategy that pulls
the most semantically useful fields. Document rows are also embedded
as-is so agents can retrieve raw evidence from uploaded reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import structlog

from remi.domain.documents.models import DocumentStore
from remi.domain.properties.ports import PropertyStore
from remi.domain.retrieval.ports import Embedder, VectorStore
from remi.domain.retrieval.types import EmbeddingRecord, EmbeddingRequest

_log = structlog.get_logger(__name__)


def _decimal_str(d: Decimal) -> str:
    return f"${d:,.2f}" if d else ""


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
    ) -> None:
        self._ps = property_store
        self._vs = vector_store
        self._embedder = embedder
        self._ds = document_store

    async def run_full(self) -> PipelineResult:
        """Re-embed all entities and document rows. Upserts by stable IDs; does not clear orphans."""
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
            for req, vec in zip(batch, vectors):
                records.append(EmbeddingRecord(
                    id=req.id,
                    text=req.text,
                    vector=vec,
                    source_entity_id=req.source_entity_id,
                    source_entity_type=req.source_entity_type,
                    source_field=req.source_field,
                    metadata=req.metadata,
                ))

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
        requests.extend(await self._extract_tenants())
        requests.extend(await self._extract_units())
        requests.extend(await self._extract_maintenance())
        requests.extend(await self._extract_properties())
        requests.extend(await self._extract_document_rows())
        return requests

    async def _extract_document_rows(self) -> list[EmbeddingRequest]:
        """Embed each row of every stored document as a searchable evidence record.

        This gives agents a second retrieval layer: raw report rows alongside
        entity-level summaries. Useful for questions that refer to specific
        values or combinations that the entity profile templates don't capture.

        Rows with fewer than 10 characters of serialized text are skipped.
        """
        if self._ds is None:
            return []

        requests: list[EmbeddingRequest] = []
        docs = await self._ds.list_documents()

        for doc in docs:
            report_type = doc.metadata.get("report_type", "unknown")
            manager_id = doc.metadata.get("manager_id", "")

            for i, row in enumerate(doc.rows):
                # Serialize as "col: val. col: val. ..." — skip blank/None values.
                parts = [
                    f"{k}: {v}"
                    for k, v in row.items()
                    if v is not None and str(v).strip()
                ]
                text = ". ".join(parts)
                if len(text.strip()) < 10:
                    continue

                requests.append(EmbeddingRequest(
                    id=f"vec:document:{doc.id}:row:{i}",
                    text=text,
                    source_entity_id=doc.id,
                    source_entity_type="DocumentRow",
                    source_field="row",
                    metadata={
                        "document_id": doc.id,
                        "filename": doc.filename,
                        "report_type": report_type,
                        "row_index": i,
                        "manager_id": manager_id,
                    },
                ))

        return requests

    # -- Text extraction per entity type --------------------------------------

    async def _extract_tenants(self) -> list[EmbeddingRequest]:
        tenants = await self._ps.list_tenants()
        requests: list[EmbeddingRequest] = []

        for t in tenants:
            parts = [f"Tenant: {t.name}"]
            if t.status:
                parts.append(f"Status: {t.status.value}")
            if t.balance_owed > 0:
                parts.append(f"Balance owed: {_decimal_str(t.balance_owed)}")
            if t.balance_30_plus > 0:
                parts.append(f"Balance 30+ days: {_decimal_str(t.balance_30_plus)}")
            if t.tags:
                parts.append(f"Tags: {', '.join(t.tags)}")
            if t.last_payment_date:
                parts.append(f"Last payment: {t.last_payment_date.isoformat()}")

            text = ". ".join(parts)
            if len(text.strip()) < 10:
                continue

            leases = await self._ps.list_leases(tenant_id=t.id)
            manager_id = ""
            property_id = ""
            if leases:
                property_id = leases[0].property_id
                prop = await self._ps.get_property(property_id)
                if prop:
                    portfolios = await self._ps.list_portfolios()
                    for pf in portfolios:
                        if pf.id == prop.portfolio_id:
                            manager_id = pf.manager_id
                            break

            requests.append(EmbeddingRequest(
                id=f"vec:tenant:{t.id}:profile",
                text=text,
                source_entity_id=t.id,
                source_entity_type="Tenant",
                source_field="profile",
                metadata={
                    "manager_id": manager_id,
                    "property_id": property_id,
                    "tenant_name": t.name,
                },
            ))
        return requests

    async def _extract_units(self) -> list[EmbeddingRequest]:
        units = await self._ps.list_units()
        requests: list[EmbeddingRequest] = []

        for u in units:
            prop = await self._ps.get_property(u.property_id)
            prop_name = prop.name if prop else u.property_id

            parts = [f"Unit {u.unit_number} at {prop_name}"]
            parts.append(f"Status: {u.status.value}")
            if u.bedrooms is not None:
                parts.append(f"{u.bedrooms}BR/{u.bathrooms or '?'}BA")
            if u.sqft:
                parts.append(f"{u.sqft} sqft")
            if u.current_rent > 0:
                parts.append(f"Current rent: {_decimal_str(u.current_rent)}")
            if u.market_rent > 0:
                parts.append(f"Market rent: {_decimal_str(u.market_rent)}")
            if u.days_vacant is not None and u.days_vacant > 0:
                parts.append(f"Vacant {u.days_vacant} days")

            text = ". ".join(parts)
            if len(text.strip()) < 10:
                continue

            manager_id = ""
            if prop:
                portfolios = await self._ps.list_portfolios()
                for pf in portfolios:
                    if pf.id == prop.portfolio_id:
                        manager_id = pf.manager_id
                        break

            requests.append(EmbeddingRequest(
                id=f"vec:unit:{u.id}:profile",
                text=text,
                source_entity_id=u.id,
                source_entity_type="Unit",
                source_field="profile",
                metadata={
                    "manager_id": manager_id,
                    "property_id": u.property_id,
                    "property_name": prop_name,
                },
            ))
        return requests

    async def _extract_maintenance(self) -> list[EmbeddingRequest]:
        requests_out: list[EmbeddingRequest] = []
        all_requests = await self._ps.list_maintenance_requests()

        for req in all_requests:
            prop = await self._ps.get_property(req.property_id)
            prop_name = prop.name if prop else req.property_id

            parts = [f"Maintenance request at {prop_name}, unit {req.unit_id}"]
            if req.title:
                parts.append(f"Title: {req.title}")
            if req.description:
                parts.append(f"Description: {req.description}")
            parts.append(f"Category: {req.category.value}")
            parts.append(f"Priority: {req.priority.value}")
            parts.append(f"Status: {req.status.value}")
            if req.vendor:
                parts.append(f"Vendor: {req.vendor}")
            if req.cost is not None:
                parts.append(f"Cost: {_decimal_str(req.cost)}")

            text = ". ".join(parts)

            manager_id = ""
            if prop:
                portfolios = await self._ps.list_portfolios()
                for pf in portfolios:
                    if pf.id == prop.portfolio_id:
                        manager_id = pf.manager_id
                        break

            requests_out.append(EmbeddingRequest(
                id=f"vec:maintenance:{req.id}:description",
                text=text,
                source_entity_id=req.id,
                source_entity_type="MaintenanceRequest",
                source_field="description",
                metadata={
                    "manager_id": manager_id,
                    "property_id": req.property_id,
                    "property_name": prop_name,
                    "priority": req.priority.value,
                    "status": req.status.value,
                },
            ))
        return requests_out

    async def _extract_properties(self) -> list[EmbeddingRequest]:
        properties = await self._ps.list_properties()
        requests: list[EmbeddingRequest] = []

        for p in properties:
            parts = [f"Property: {p.name}"]
            if p.address:
                parts.append(f"Address: {p.address.one_line()}")
            parts.append(f"Type: {p.property_type.value}")
            if p.year_built:
                parts.append(f"Built: {p.year_built}")

            text = ". ".join(parts)

            manager_id = ""
            portfolios = await self._ps.list_portfolios()
            for pf in portfolios:
                if pf.id == p.portfolio_id:
                    manager_id = pf.manager_id
                    break

            requests.append(EmbeddingRequest(
                id=f"vec:property:{p.id}:profile",
                text=text,
                source_entity_id=p.id,
                source_entity_type="Property",
                source_field="profile",
                metadata={
                    "manager_id": manager_id,
                    "portfolio_id": p.portfolio_id,
                    "property_name": p.name,
                },
            ))
        return requests
