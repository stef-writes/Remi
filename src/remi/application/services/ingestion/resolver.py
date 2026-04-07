"""Type coercion, address parsing, and enum maps for ingestion rows.

Pure leaf module — zero I/O, zero LLM. Imported by persisters, context,
and matcher. Every function is deterministic and safe to call on arbitrary
user-supplied strings.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from remi.application.core.models.address import Address
from remi.application.core.models.enums import (
    MaintenanceStatus,
    Priority,
    TenantStatus,
    TradeCategory,
)

# ---------------------------------------------------------------------------
# Entity types that have ROW_PERSISTERS in persisters.py
# ---------------------------------------------------------------------------

PERSISTABLE_TYPES: frozenset[str] = frozenset(
    {
        "Unit",
        "Tenant",
        "Lease",
        "BalanceObservation",
        "Property",
        "MaintenanceRequest",
        "Owner",
        "Vendor",
        "PropertyManager",
    }
)

# ---------------------------------------------------------------------------
# Sentinel dates for leases without explicit bounds
# ---------------------------------------------------------------------------

LEASE_START_FALLBACK = date(2000, 1, 1)
LEASE_END_FALLBACK = date(2099, 12, 31)

# ---------------------------------------------------------------------------
# Enum maps — raw report strings to domain enums
# ---------------------------------------------------------------------------

TENANT_STATUS_MAP: dict[str, TenantStatus] = {
    "current": TenantStatus.CURRENT,
    "notice": TenantStatus.NOTICE,
    "demand": TenantStatus.DEMAND,
    "filing": TenantStatus.FILING,
    "hearing": TenantStatus.HEARING,
    "judgment": TenantStatus.JUDGMENT,
    "evict": TenantStatus.EVICT,
    "eviction": TenantStatus.EVICT,
    "past": TenantStatus.PAST,
}

MAINTENANCE_CATEGORY_MAP: dict[str, TradeCategory] = {
    "plumbing": TradeCategory.PLUMBING,
    "electrical": TradeCategory.ELECTRICAL,
    "hvac": TradeCategory.HVAC,
    "appliance": TradeCategory.APPLIANCE,
    "structural": TradeCategory.STRUCTURAL,
    "general": TradeCategory.GENERAL,
    "cleaning": TradeCategory.CLEANING,
    "painting": TradeCategory.PAINTING,
    "flooring": TradeCategory.FLOORING,
    "roofing": TradeCategory.ROOFING,
    "landscaping": TradeCategory.LANDSCAPING,
    "other": TradeCategory.OTHER,
}

MAINTENANCE_STATUS_MAP: dict[str, MaintenanceStatus] = {
    "open": MaintenanceStatus.OPEN,
    "in_progress": MaintenanceStatus.IN_PROGRESS,
    "in progress": MaintenanceStatus.IN_PROGRESS,
    "completed": MaintenanceStatus.COMPLETED,
    "complete": MaintenanceStatus.COMPLETED,
    "closed": MaintenanceStatus.COMPLETED,
    "cancelled": MaintenanceStatus.CANCELLED,
    "canceled": MaintenanceStatus.CANCELLED,
}

PRIORITY_MAP: dict[str, Priority] = {
    "low": Priority.LOW,
    "medium": Priority.MEDIUM,
    "normal": Priority.MEDIUM,
    "high": Priority.HIGH,
    "urgent": Priority.URGENT,
    "emergency": Priority.EMERGENCY,
}

# ---------------------------------------------------------------------------
# Type coercion — safe on arbitrary user-supplied strings
# ---------------------------------------------------------------------------

_DATE_FORMATS = (
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%b %d, %Y",
)


def to_date(val: object) -> date | None:
    """Best-effort date parsing. Returns None on failure."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    text = str(val).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


_CURRENCY_STRIP_RE = re.compile(r"[$,\s]")
_PARENS_RE = re.compile(r"^\((.+)\)$")


def to_decimal(val: object) -> Decimal:
    """Parse a currency/numeric value into Decimal. Returns 0 on failure."""
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    text = _CURRENCY_STRIP_RE.sub("", str(val).strip())
    if not text:
        return Decimal("0")
    m = _PARENS_RE.match(text)
    if m:
        text = f"-{m.group(1)}"
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def to_int(val: object) -> int | None:
    """Safe integer coercion. Returns None on failure."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Address / property name helpers
# ---------------------------------------------------------------------------

_STREET_SUFFIXES = frozenset({
    "st", "ave", "avenue", "blvd", "boulevard", "ct", "court", "dr", "drive",
    "ln", "lane", "pl", "place", "rd", "road", "sq", "street", "ter",
    "terrace", "way", "cir", "circle", "pkwy", "parkway", "hwy", "highway",
    "run", "alley", "aly",
})

# Two-comma: "123 Main St, Pittsburgh, PA 15203"
_CITY_STATE_ZIP_RE = re.compile(r",\s*([A-Za-z\s]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$")

# Trailing ", ST ZIP" (single-comma / AppFolio): "123 Main St Pittsburgh, PA 15203"
_STATE_ZIP_RE = re.compile(r",\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$")

_TRAILING_STATE_RE = re.compile(r",\s*([A-Z]{2})\s*$")


def _split_address(raw: str) -> tuple[str, str, str, str]:
    """Split a raw address into (street, city, state, zip).

    Handles both standard and AppFolio formats:
      "123 Main St, Pittsburgh, PA 15203"   → two-comma
      "123 Main St Pittsburgh, PA 15203"    → single-comma (AppFolio)
      "100 Smithfield St - 100 Smithfield St Pittsburgh, PA 15222" → AppFolio with dash
    """
    addr = raw.strip()
    if not addr:
        return ("", "", "", "")

    # Two-comma format: "Street, City, ST ZIP"
    m = _CITY_STATE_ZIP_RE.search(addr)
    if m:
        street = addr[: m.start()].strip().rstrip(",")
        return (street, m.group(1).strip(), m.group(2), m.group(3))

    # Single-comma format: "Street City, ST ZIP"
    # Common in AppFolio: "100 Smithfield St Pittsburgh, PA 15222"
    # Zip is captured above. City is the last word(s) before the comma.
    # We can't reliably distinguish "St" (street) from a city name using
    # casing alone, so we use a simple heuristic: scan backwards from the
    # comma collecting words that are NOT common street suffixes.
    m = _STATE_ZIP_RE.search(addr)
    if m:
        before_comma = addr[: m.start()].strip()
        state = m.group(1)
        zipcode = m.group(2)
        tokens = before_comma.split()
        city_parts: list[str] = []
        for tok in reversed(tokens):
            low = tok.lower().rstrip(".")
            if low in _STREET_SUFFIXES or not tok[0].isupper():
                break
            city_parts.insert(0, tok)
        if city_parts:
            city = " ".join(city_parts)
            street = before_comma[: before_comma.rfind(city_parts[0])].strip()
        else:
            city = ""
            street = before_comma
        return (street, city, state, zipcode)

    # Trailing state only: "123 Main St, PA"
    m = _TRAILING_STATE_RE.search(addr)
    if m:
        street = addr[: m.start()].strip().rstrip(",")
        return (street, "", m.group(1), "")

    return (addr, "", "", "")


def property_name(address: str) -> str:
    """Extract the canonical short name from a full address.

    Strips city/state/zip suffix:
      "123 Main St, Pittsburgh, PA 15203" -> "123 Main St"
      "123 Main St Pittsburgh, PA 15203"  -> "123 Main St"
    """
    street, city, state, zipcode = _split_address(address)
    return street if street else address.strip()


def parse_address(raw: str) -> Address:
    """Split a raw address string into an Address model.

    Handles both standard and AppFolio address formats:
      "123 Main St, Pittsburgh, PA 15203"  (two commas)
      "123 Main St Pittsburgh, PA 15203"   (single comma)
    """
    street, city, state, zipcode = _split_address(raw)
    return Address(
        street=street or raw.strip(),
        city=city,
        state=state,
        zip_code=zipcode,
    )
