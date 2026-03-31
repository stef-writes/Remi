"""Shared parsing helpers for ingestion modules."""

from __future__ import annotations

import re
from typing import Any

from remi.documents.appfolio_schema import parse_property_name
from remi.models.properties import Address, OccupancyStatus, UnitStatus
from remi.shared.text import manager_name_from_tag, slugify


def parse_address(full_address: str) -> Address:
    """Best-effort address parsing from AppFolio's combined address string."""
    name = parse_property_name(full_address)
    parts = full_address.rsplit(",", 1)
    city = "Pittsburgh"
    state = "PA"
    zip_code = ""
    if len(parts) >= 2:
        tail = parts[1].strip()
        state_zip = tail.split()
        if len(state_zip) >= 2:
            state = state_zip[0]
            zip_code = state_zip[1]
        elif len(state_zip) == 1:
            state = state_zip[0]
    return Address(street=name, city=city, state=state, zip_code=zip_code)


def occupancy_to_unit_status(occ: OccupancyStatus | None) -> UnitStatus:
    """Map AppFolio occupancy to the simpler UnitStatus enum."""
    if occ is None:
        return UnitStatus.VACANT
    if occ == OccupancyStatus.OCCUPIED:
        return UnitStatus.OCCUPIED
    if occ in (OccupancyStatus.NOTICE_RENTED, OccupancyStatus.NOTICE_UNRENTED):
        return UnitStatus.OCCUPIED
    return UnitStatus.VACANT


def entity_id_from_row(entity_type: str, row: dict[str, Any], row_idx: int, doc_id: str) -> str:
    for key in ("id", f"{entity_type}_id", f"{entity_type}Id", "ID"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return f"{entity_type}:{val}"
    name_keys = ("name", f"{entity_type}_name", "title", "label")
    for key in name_keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            slug = re.sub(r"[^a-z0-9]+", "-", str(val).lower().strip())[:40]
            return f"{entity_type}:{slug}"
    return f"{entity_type}:{doc_id}:row-{row_idx}"


# Re-export public helpers from shared.text
__all__ = [
    "entity_id_from_row",
    "manager_name_from_tag",
    "occupancy_to_unit_status",
    "parse_address",
    "slugify",
]
