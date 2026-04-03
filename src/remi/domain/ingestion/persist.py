"""Persistence orchestrator — resolve LLM rows and write to stores + KG.

Coordinates the two-pass ingestion process (manager-tag collection, then
per-row persist). Shared context and KB helpers live in ``context.py``;
per-entity handlers live in ``persisters.py``.
"""

from __future__ import annotations

from typing import Any

import structlog

from remi.agent.graph.stores import KnowledgeStore
from remi.domain.ingestion.base import IngestionResult, RowWarning
from remi.domain.ingestion.context import IngestionCtx
from remi.domain.ingestion.managers import (
    ManagerResolver,
    classify_manager_values,
)
from remi.domain.ingestion.persisters import ROW_PERSISTERS
from remi.domain.ingestion.resolver import property_name, resolve_row_type
from remi.domain.portfolio.protocols import PropertyStore
from remi.types.text import slugify

_log = structlog.get_logger(__name__)


async def resolve_and_persist(
    rows: list[dict[str, Any]],
    *,
    report_type: str,
    platform: str,
    doc_id: str,
    namespace: str,
    kb: KnowledgeStore,
    ps: PropertyStore,
    manager_resolver: ManagerResolver,
    result: IngestionResult,
    upload_portfolio_id: str | None = None,
) -> None:
    """Map LLM-extracted rows to domain models and persist in one pass."""
    if not rows:
        return

    ctx = IngestionCtx(
        platform=platform, report_type=report_type, doc_id=doc_id,
        namespace=namespace, kb=kb, ps=ps,
        manager_resolver=manager_resolver, result=result,
        upload_portfolio_id=upload_portfolio_id,
    )

    for row in rows:
        rt = resolve_row_type(row.get("type", "raw_row"))
        if rt in ("Unit", "Tenant", "Lease", "Property"):
            _collect_manager_tag(row, ctx)
    ctx.real_manager_tags = classify_manager_values(ctx.prop_manager_tags)

    for i, row in enumerate(rows):
        rt = resolve_row_type(row.get("type", "raw_row"))
        handler = ROW_PERSISTERS.get(rt)
        if handler is None:
            ctx.result.rows_skipped += 1
            continue
        try:
            await handler(row, ctx)
            ctx.result.rows_accepted += 1
        except Exception:
            _log.warning("row_persist_failed", row_type=rt,
                         doc_id=doc_id, exc_info=True)
            ctx.result.persist_errors.append(RowWarning(
                row_index=i, row_type=rt, field="*",
                issue="persist_failed",
                raw_value=str(row.get("property_address", ""))[:100],
            ))
            ctx.result.rows_rejected += 1

    _log.info(
        "resolve_complete", namespace=namespace,
        entities=result.entities_created,
        relationships=result.relationships_created,
        rows_accepted=result.rows_accepted,
        rows_rejected=result.rows_rejected,
        rows_skipped=result.rows_skipped,
        real_managers=len(ctx.real_manager_tags),
        tags_skipped=len(result.manager_tags_skipped),
    )


def _collect_manager_tag(row: dict[str, Any], ctx: IngestionCtx) -> None:
    raw_addr = str(row.get("property_address", "")).strip()
    name = property_name(raw_addr) or raw_addr
    prop_id = slugify(f"property:{name}")
    tags_raw = str(row.get("tags") or "").strip()
    manager_raw = str(
        row.get("manager_name") or row.get("manager")
        or row.get("site_manager_name") or ""
    ).strip()
    tag = None
    if tags_raw:
        parts = [t.strip() for t in tags_raw.split(",") if t.strip()]
        tag = next(
            (t for t in parts if t.lower() != "month-to-month"), None,
        )
    if not tag and manager_raw:
        tag = manager_raw
    if tag and prop_id not in ctx.prop_manager_tags:
        ctx.prop_manager_tags[prop_id] = tag
