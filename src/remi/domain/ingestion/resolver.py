"""Schema-driven row resolution — LLM row type names to domain model helpers.

Maps LLM-extracted row types to canonical ontology names and provides
type-coercion helpers (strings to enums, decimals, dates) shared by the
persistence layer in ``persist.py``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import structlog

from remi.domain.portfolio.models import (
    Address,
    MaintenanceCategory,
    MaintenanceStatus,
    OccupancyStatus,
    Priority,
    TenantStatus,
    UnitStatus,
)

_log = structlog.get_logger(__name__)

LEASE_START_FALLBACK = date(2000, 1, 1)
LEASE_END_FALLBACK = date(2099, 12, 31)


# ---------------------------------------------------------------------------
# Type resolution — ontology names + legacy compat
# ---------------------------------------------------------------------------

LEGACY_TYPE_MAP: dict[str, str] = {
    "unit": "Unit",
    "tenant_balance": "Tenant",
    "lease": "Lease",
    "property": "Property",
}


def resolve_row_type(raw_type: str) -> str:
    """Map legacy/lowercase type names to canonical ontology names."""
    return LEGACY_TYPE_MAP.get(raw_type, raw_type)


PERSISTABLE_TYPES: frozenset[str] = frozenset(
    {"Unit", "Tenant", "Lease", "Property", "MaintenanceRequest",
     "Owner", "Vendor"}
)


# ---------------------------------------------------------------------------
# Enum mapping tables
# ---------------------------------------------------------------------------

OCCUPANCY_MAP: dict[str, OccupancyStatus] = {
    "occupied": OccupancyStatus.OCCUPIED,
    "notice_rented": OccupancyStatus.NOTICE_RENTED,
    "notice_unrented": OccupancyStatus.NOTICE_UNRENTED,
    "vacant_rented": OccupancyStatus.VACANT_RENTED,
    "vacant_unrented": OccupancyStatus.VACANT_UNRENTED,
}

TENANT_STATUS_MAP: dict[str, TenantStatus] = {
    "current": TenantStatus.CURRENT,
    "notice": TenantStatus.NOTICE,
    "demand": TenantStatus.DEMAND,
    "filing": TenantStatus.FILING,
    "hearing": TenantStatus.HEARING,
    "judgment": TenantStatus.JUDGMENT,
    "evict": TenantStatus.EVICT,
    "past": TenantStatus.PAST,
}

UNIT_STATUS_FROM_OCCUPANCY: dict[OccupancyStatus, UnitStatus] = {
    OccupancyStatus.OCCUPIED: UnitStatus.OCCUPIED,
    OccupancyStatus.NOTICE_RENTED: UnitStatus.OCCUPIED,
    OccupancyStatus.NOTICE_UNRENTED: UnitStatus.OCCUPIED,
    OccupancyStatus.VACANT_RENTED: UnitStatus.VACANT,
    OccupancyStatus.VACANT_UNRENTED: UnitStatus.VACANT,
}

MAINTENANCE_CATEGORY_MAP: dict[str, MaintenanceCategory] = {
    v.value: v for v in MaintenanceCategory
}
MAINTENANCE_STATUS_MAP: dict[str, MaintenanceStatus] = {
    v.value: v for v in MaintenanceStatus
}
PRIORITY_MAP: dict[str, Priority] = {v.value: v for v in Priority}


# ---------------------------------------------------------------------------
# Parsing / coercion helpers
# ---------------------------------------------------------------------------


def property_name(full_address: str) -> str:
    """Extract the property name from a full address string."""
    if " - " in full_address:
        return full_address.split(" - ")[0].strip()
    parts = full_address.split(",")
    return parts[0].strip() if len(parts) >= 2 else full_address.strip()


def parse_address(raw: str) -> Address:
    """Parse a raw address string into an Address model."""
    name = property_name(raw)
    parts = raw.rsplit(",", 1)
    city, state, zip_code = "Unknown", "XX", ""
    if len(parts) >= 2:
        tail = parts[1].strip().split()
        if len(tail) >= 2:
            state, zip_code = tail[0], tail[1]
        elif tail:
            state = tail[0]
    return Address(street=name, city=city, state=state, zip_code=zip_code)


def to_decimal(val: Any, default: str = "0") -> Decimal:
    """Coerce a value to Decimal, falling back to *default*."""
    if val is None:
        return Decimal(default)
    try:
        return Decimal(str(val))
    except Exception:
        _log.warning(
            "decimal_parse_fallback",
            raw_value=str(val)[:50],
            default=default,
        )
        return Decimal(default)


def to_date(val: Any) -> date | None:
    """Coerce a value to a date, trying common formats."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    from datetime import datetime as _dt

    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return _dt.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def to_int(val: Any) -> int | None:
    """Coerce a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
