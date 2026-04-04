"""Multi-source text extraction for the embedding pipeline.

These extractors aggregate across multiple stores (PropertyStore +
SignalStore, or DocumentStore) to build rich embedding text.
Single-entity extractors that only need a PropertyStore live in
``extraction.py``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from remi.agent.documents.types import DocumentStore
from remi.agent.signals import SignalStore
from remi.agent.vectors.types import EmbeddingRequest
from remi.application.core.protocols import PropertyStore

_log = structlog.get_logger(__name__)


def _decimal_str(d: Decimal) -> str:
    return f"${d:,.2f}" if d else ""


async def extract_managers(
    ps: PropertyStore,
    ss: SignalStore | None,
) -> list[EmbeddingRequest]:
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


async def extract_document_rows(ds: DocumentStore) -> list[EmbeddingRequest]:
    """Embed each row of every stored document as a searchable evidence record.

    Rows with fewer than 10 characters of serialized text are skipped.
    """
    requests: list[EmbeddingRequest] = []
    docs = await ds.list_documents()

    for doc in docs:
        report_type = doc.metadata.get("report_type", "unknown")
        manager_id = doc.metadata.get("manager_id", "")

        for i, row in enumerate(doc.rows):
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
