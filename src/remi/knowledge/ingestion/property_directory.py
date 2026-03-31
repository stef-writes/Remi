"""AppFolio Property Directory report ingestion.

This module handles exports that list all active properties alongside their
assigned property manager.  The key jobs are:

  1. Create PropertyManager + Portfolio records for every manager found.
  2. Upsert Property records, linking them to the correct portfolio.
  3. Leave properties with no manager column value as portfolio_id="" so
     they appear in the /dashboard/needs-manager endpoint.

Column definitions are filled in once we have a real AppFolio export to
calibrate against.  Until then, the parser falls back to heuristic column
matching and logs which columns it found / missed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from remi.knowledge.ingestion.helpers import parse_address
from remi.shared.text import slugify

if TYPE_CHECKING:
    from remi.knowledge.ingestion.base import IngestionResult
    from remi.models.documents import Document
    from remi.models.memory import KnowledgeStore
    from remi.models.properties import PropertyStore

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Column name candidates — will be tightened once we see the real export.
# Listed in order of preference; first hit wins.
# ---------------------------------------------------------------------------

_PROPERTY_COL_CANDIDATES = ["Property", "Property Name", "Building", "Address", "Location"]
_MANAGER_COL_CANDIDATES = ["Property Manager", "Manager", "Managed By", "PM", "Tags"]
_ADDRESS_COL_CANDIDATES = ["Address", "Full Address", "Street", "Property Address"]
_STATUS_COL_CANDIDATES = ["Status", "Active", "Property Status"]


def _first_match(row: dict[str, Any], candidates: list[str]) -> str | None:
    for key in candidates:
        if key in row and row[key] is not None:
            val = str(row[key]).strip()
            if val:
                return val
    return None


async def ingest_property_directory(
    doc: Document,
    namespace: str,
    result: IngestionResult,
    kb: KnowledgeStore,
    ps: PropertyStore,
    upsert_entity: Any,
    upsert_property_safe: Any,
    ensure_manager: Any,
    upload_portfolio_id: str | None = None,
) -> None:
    if not doc.rows:
        logger.warning("property_directory_empty", doc_id=doc.id)
        return

    sample = doc.rows[0]
    found_cols = set(sample.keys())
    logger.info(
        "property_directory_columns_detected",
        doc_id=doc.id,
        columns=sorted(found_cols),
    )

    rows_with_manager = 0
    rows_without_manager = 0

    for row in doc.rows:
        prop_raw = _first_match(row, _PROPERTY_COL_CANDIDATES)
        if not prop_raw:
            result.ambiguous_rows.append(row)
            continue

        # Use the property value as both name and address hint until we know
        # which column is the canonical address in this export.
        addr_raw = _first_match(row, _ADDRESS_COL_CANDIDATES) or prop_raw
        manager_raw = _first_match(row, _MANAGER_COL_CANDIDATES)

        prop_id = slugify(f"property:{prop_raw}")

        prop_kb_props: dict[str, Any] = {
            "name": prop_raw,
            "address": addr_raw,
            "source_doc": doc.id,
        }
        if manager_raw:
            prop_kb_props["manager_tag"] = manager_raw
        status = _first_match(row, _STATUS_COL_CANDIDATES)
        if status:
            prop_kb_props["status"] = status

        await upsert_entity(prop_id, "appfolio_property", namespace, prop_kb_props, result)

        portfolio_id: str | None = upload_portfolio_id
        if portfolio_id is None and manager_raw:
            portfolio_id = await ensure_manager(manager_raw)

        if manager_raw:
            rows_with_manager += 1
        else:
            rows_without_manager += 1

        addr = parse_address(addr_raw)
        await upsert_property_safe(prop_id, prop_raw, addr, portfolio_id=portfolio_id)

    logger.info(
        "property_directory_ingest_complete",
        doc_id=doc.id,
        rows_with_manager=rows_with_manager,
        rows_without_manager=rows_without_manager,
        ambiguous=len(result.ambiguous_rows),
    )
