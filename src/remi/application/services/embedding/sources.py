"""Multi-source text extraction for the embedding pipeline.

These extractors aggregate across multiple stores (PropertyStore +
signal store, ContentStore) to build rich embedding text.
Single-entity extractors that only need a PropertyStore live in
``extraction.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

import structlog

from remi.agent.documents import ContentStore
from remi.application.core.protocols import EmbedRequest, PropertyStore

_log = structlog.get_logger(__name__)


@runtime_checkable
class SignalStoreProtocol(Protocol):
    """Minimal protocol for listing signals — avoids importing agent.signals."""

    async def list_signals(self) -> Sequence[Any]: ...


def _decimal_str(d: Decimal) -> str:
    return f"${d:,.2f}" if d else ""


async def extract_managers(
    ps: PropertyStore,
    ss: SignalStoreProtocol | None,
) -> list[EmbedRequest]:
    """Build rich embedding text per manager by aggregating portfolio metrics."""
    managers = await ps.list_managers()
    if not managers:
        return []

    all_portfolios = await ps.list_portfolios()
    all_units = await ps.list_units()
    all_tenants = await ps.list_tenants()
    all_maintenance = await ps.list_maintenance_requests()

    signals_by_manager: dict[str, dict[str, int]] = {}
    if ss is not None:
        try:
            all_signals = await ss.list_signals()
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

    unit_by_property: dict[str, list[Any]] = {}
    for u in all_units:
        unit_by_property.setdefault(u.property_id, []).append(u)

    tenant_balances: dict[str, list[Any]] = {}
    for t in all_tenants:
        if t.balance_owed > 0:
            leases = await ps.list_leases(tenant_id=t.id)
            for lease in leases:
                tenant_balances.setdefault(lease.property_id, []).append(t)

    maintenance_by_property: dict[str, int] = {}
    for req in all_maintenance:
        if req.status.value in ("open", "pending", "in_progress"):
            maintenance_by_property[req.property_id] = (
                maintenance_by_property.get(req.property_id, 0) + 1
            )

    requests: list[EmbedRequest] = []
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

        parts.append(f"Manages {property_count} properties with {total_units} total units")

        status_parts: list[str] = []
        if vacancy_count:
            status_parts.append(f"{vacancy_count} vacancies")
        if delinquent_count:
            status_parts.append(
                f"{delinquent_count} delinquent tenants"
                f" (balance {_decimal_str(delinquent_balance)})"
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
            EmbedRequest(
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


async def extract_document_rows(
    content_store: ContentStore,
    ps: PropertyStore,
) -> list[EmbedRequest]:
    """Embed each row of every stored tabular document as a searchable evidence record.

    Scope metadata from the promoted Document model flows into embedding records.
    """
    requests: list[EmbedRequest] = []
    contents = await content_store.list_documents()
    doc_index = {d.id: d for d in await ps.list_documents()}

    for content in contents:
        if content.kind.value != "tabular":
            continue

        doc_meta = doc_index.get(content.id)
        report_type = doc_meta.report_type if doc_meta else "unknown"
        manager_id = doc_meta.manager_id if doc_meta else None
        unit_id = doc_meta.unit_id if doc_meta else None
        property_id = doc_meta.property_id if doc_meta else None

        for i, row in enumerate(content.rows):
            parts = [f"{k}: {v}" for k, v in row.items() if v is not None and str(v).strip()]
            text = ". ".join(parts)
            if len(text.strip()) < 10:
                continue

            meta: dict[str, Any] = {
                "document_id": content.id,
                "filename": content.filename,
                "report_type": report_type,
                "row_index": i,
            }
            if manager_id:
                meta["manager_id"] = manager_id
            if unit_id:
                meta["unit_id"] = unit_id
            if property_id:
                meta["property_id"] = property_id

            requests.append(
                EmbedRequest(
                    id=f"vec:document:{content.id}:row:{i}",
                    text=text,
                    source_entity_id=content.id,
                    source_entity_type="DocumentRow",
                    source_field="row",
                    metadata=meta,
                )
            )

    return requests


async def extract_document_chunks(
    content_store: ContentStore,
    ps: PropertyStore,
) -> list[EmbedRequest]:
    """Embed each text chunk of every stored text document as a searchable passage."""
    requests: list[EmbedRequest] = []
    contents = await content_store.list_documents()
    doc_index = {d.id: d for d in await ps.list_documents()}

    for content in contents:
        if content.kind.value != "text":
            continue

        doc_meta = doc_index.get(content.id)
        manager_id = doc_meta.manager_id if doc_meta else None
        unit_id = doc_meta.unit_id if doc_meta else None
        property_id = doc_meta.property_id if doc_meta else None

        for chunk in content.chunks:
            if len(chunk.text.strip()) < 10:
                continue

            meta: dict[str, Any] = {
                "document_id": content.id,
                "filename": content.filename,
                "page": chunk.page,
                "chunk_index": chunk.index,
                "tags": ",".join(content.tags),
            }
            if manager_id:
                meta["manager_id"] = manager_id
            if unit_id:
                meta["unit_id"] = unit_id
            if property_id:
                meta["property_id"] = property_id

            requests.append(
                EmbedRequest(
                    id=f"vec:document:{content.id}:chunk:{chunk.index}",
                    text=chunk.text,
                    source_entity_id=content.id,
                    source_entity_type="DocumentChunk",
                    source_field="chunk",
                    metadata=meta,
                )
            )

    return requests
