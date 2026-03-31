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

import structlog

from remi.models.documents import DocumentStore
from remi.models.properties import PropertyStore
from remi.models.retrieval import Embedder, EmbeddingRecord, EmbeddingRequest, VectorStore
from remi.models.signals import SignalStore

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
        requests.extend(await self._extract_managers())
        requests.extend(await self._extract_tenants())
        requests.extend(await self._extract_units())
        requests.extend(await self._extract_maintenance())
        requests.extend(await self._extract_properties())
        requests.extend(await self._extract_document_rows())
        return requests

    async def _extract_managers(self) -> list[EmbeddingRequest]:
        """Build rich embedding text per manager by aggregating portfolio metrics."""
        managers = await self._ps.list_managers()
        if not managers:
            return []

        all_portfolios = await self._ps.list_portfolios()
        all_units = await self._ps.list_units()
        all_tenants = await self._ps.list_tenants()
        all_maintenance = await self._ps.list_maintenance_requests()

        signals_by_manager: dict[str, dict[str, int]] = {}
        if self._ss is not None:
            try:
                all_signals = await self._ss.list_signals()
                for s in all_signals:
                    mgr = getattr(s, "manager_id", None) or (s.evidence or {}).get("manager_id", "")
                    if not mgr:
                        continue
                    sev = s.severity.value if hasattr(s.severity, "value") else str(s.severity)
                    bucket = signals_by_manager.setdefault(mgr, {})
                    bucket[sev] = bucket.get(sev, 0) + 1
            except Exception:
                _log.debug("manager_signal_aggregation_failed", exc_info=True)

        portfolio_by_manager: dict[str, list[str]] = {}
        for pf in all_portfolios:
            portfolio_by_manager.setdefault(pf.manager_id, []).extend(pf.property_ids)

        unit_by_property: dict[str, list] = {}
        for u in all_units:
            unit_by_property.setdefault(u.property_id, []).append(u)

        tenant_balances: dict[str, list] = {}
        for t in all_tenants:
            if t.balance_owed > 0:
                leases = await self._ps.list_leases(tenant_id=t.id)
                for lease in leases:
                    tenant_balances.setdefault(lease.property_id, []).append(t)

        maintenance_by_property: dict[str, int] = {}
        for req in all_maintenance:
            if req.status.value in ("open", "pending", "in_progress"):
                maintenance_by_property[req.property_id] = (
                    maintenance_by_property.get(req.property_id, 0) + 1
                )

        requests: list[EmbeddingRequest] = []
        for mgr in managers:
            prop_ids = portfolio_by_manager.get(mgr.id, [])
            property_count = len(prop_ids)

            total_units = 0
            vacancy_count = 0
            for pid in prop_ids:
                units_at_prop = unit_by_property.get(pid, [])
                total_units += len(units_at_prop)
                vacancy_count += sum(1 for u in units_at_prop if u.status.value == "vacant")

            delinquent_count = 0
            delinquent_balance = Decimal(0)
            for pid in prop_ids:
                for t in tenant_balances.get(pid, []):
                    delinquent_count += 1
                    delinquent_balance += t.balance_owed

            open_maintenance = sum(maintenance_by_property.get(pid, 0) for pid in prop_ids)

            parts = [f"Property manager: {mgr.name}"]
            if mgr.company:
                parts[0] += f" ({mgr.company})"
            if mgr.email:
                parts.append(f"Email: {mgr.email}")

            parts.append(
                f"Manages {property_count} properties with {total_units} total units"
            )

            status_parts: list[str] = []
            if vacancy_count:
                status_parts.append(f"{vacancy_count} vacancies")
            if delinquent_count:
                status_parts.append(
                    f"{delinquent_count} delinquent tenants (balance {_decimal_str(delinquent_balance)})"
                )
            if open_maintenance:
                status_parts.append(f"{open_maintenance} open maintenance requests")
            if status_parts:
                parts.append("Currently: " + ", ".join(status_parts))

            sev_counts = signals_by_manager.get(mgr.id, {})
            if sev_counts:
                signal_parts = []
                for sev in ("critical", "high", "medium", "low"):
                    count = sev_counts.get(sev, 0)
                    if count:
                        signal_parts.append(f"{count} {sev}")
                if signal_parts:
                    parts.append("Active signals: " + ", ".join(signal_parts))

            text = ". ".join(parts)

            portfolios_for_mgr = [pf for pf in all_portfolios if pf.manager_id == mgr.id]
            requests.append(
                EmbeddingRequest(
                    id=f"vec:manager:{mgr.id}:profile",
                    text=text,
                    source_entity_id=mgr.id,
                    source_entity_type="PropertyManager",
                    source_field="profile",
                    metadata={
                        "manager_id": mgr.id,
                        "manager_name": mgr.name,
                        "company": mgr.company or "",
                        "portfolio_count": len(portfolios_for_mgr),
                        "property_count": property_count,
                    },
                )
            )

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
                parts = [f"{k}: {v}" for k, v in row.items() if v is not None and str(v).strip()]
                text = ". ".join(parts)
                if len(text.strip()) < 10:
                    continue

                requests.append(
                    EmbeddingRequest(
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
                    )
                )

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

            requests.append(
                EmbeddingRequest(
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
                )
            )
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

            requests.append(
                EmbeddingRequest(
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
                )
            )
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

            requests_out.append(
                EmbeddingRequest(
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
                )
            )
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

            requests.append(
                EmbeddingRequest(
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
                )
            )
        return requests
