"""AppFolio-specific data sanitation helpers.

Column mapping and report-type detection now live in the LLM extraction
pipeline (application/agents/document_ingestion/app.yaml). This module
retains only the domain knowledge that is purely deterministic and would
be wrong to put in a prompt:

  - Junk property filtering: AppFolio internal bookkeeping entries that are
    not real rental properties.
  - Address normalization: strip "DO NOT USE" prefixes so the same property
    has the same ID regardless of which report it came from.
  - BD/BA parsing: split "2/1" or "3 / 2.5" into separate bedrooms/bathrooms.
  - Section header detection: identify rows that carry context (property
    address, occupancy section label) rather than data.

These functions are used by persist.py after the LLM has produced a
column-mapped row dict.
"""

from __future__ import annotations

from typing import Any

import structlog

_log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Junk property filtering
# AppFolio internal bookkeeping entries that are not real rental properties.
# ---------------------------------------------------------------------------

_JUNK_PREFIXES = (
    "1234 ",
    "1234-",
    "auto loan",
    "bank reconciliation",
    "citizens corporate",
    "fnb corporate",
    "gordon garage",
    "pbc supply",
    "ramp",
    "riva ridge corporate",
    "sycamore lot",
    "vail",
)

_JUNK_CONTAINS = frozenset(
    {
        "holiday",
        "pto",
        "morning meeting",
        "renovation meeting",
        "staging",
        "must enter address",
        "outside project",
    }
)


def is_junk_property(address: str) -> bool:
    """True when the address is an AppFolio internal bookkeeping entry."""
    lower = address.lower()
    if any(lower.startswith(p) for p in _JUNK_PREFIXES):
        return True
    return any(kw in lower for kw in _JUNK_CONTAINS)


# ---------------------------------------------------------------------------
# Address normalization
# ---------------------------------------------------------------------------

_DO_NOT_USE_PREFIXES = ("DO NOT USE - ", "DO NOT USE-", "DO NOT USE ")

# AppFolio property directory format: "<display label> - <full address>"
# The label is always a prefix of the address, e.g.:
#   "1 Crosman St - 1 Crosman St Pittsburgh, PA 15203"
#   "1 Pius Street - C6 - 1 Pius Street Unit C6 Pittsburgh, PA 15203"
#   "101-103 E Agnew Avenue - 101-103 E Agnew Avenue Pittsburgh, PA 15210"
#
# Strategy: try every " - " split point; if the part after the split starts
# with the label (case-insensitive), the label is redundant — strip it.
# We scan left-to-right so the first matching split wins (shortest label).
#
# Handles the tricky unit-suffix case:
#   "1 Pius Street - C6 - 1 Pius Street Unit C6 Pittsburgh, PA 15203"
#   Split 1: label="1 Pius Street", remainder="C6 - 1 Pius Street Unit C6..."
#            → no match (remainder starts with "C6", not "1 Pius")
#   Split 2: label="1 Pius Street - C6", remainder="1 Pius Street Unit C6..."
#            → no match (label has " - " in it, remainder doesn't start with it)
# For this pattern the remainder after the LAST " - " is the canonical address:
#   "1 Pius Street Unit C6 Pittsburgh, PA 15203"
# So if no early split matches, we also try: does stripping everything up to
# the last " - " produce a remainder that starts with a street number?
def _strip_appfolio_label(address: str) -> str:
    sep = " - "
    start = 0
    while True:
        idx = address.find(sep, start)
        if idx == -1:
            break
        label = address[:idx].strip()
        remainder = address[idx + len(sep):]
        if label and remainder.lower().startswith(label.lower()):
            return remainder.strip()
        start = idx + len(sep)

    # Fallback: if the string has multiple " - " segments and the last segment
    # starts with a digit (street number), take it — it's the canonical address.
    last_idx = address.rfind(sep)
    if last_idx > 0:
        last_part = address[last_idx + len(sep):].strip()
        if last_part and last_part[0].isdigit():
            return last_part

    return address


def normalize_address(address: str) -> str:
    """Strip AppFolio label prefixes and 'DO NOT USE' prefixes from addresses."""
    address = _strip_appfolio_label(address)
    for prefix in _DO_NOT_USE_PREFIXES:
        if address.upper().startswith(prefix.upper()):
            return address[len(prefix):].strip()
    return address


# ---------------------------------------------------------------------------
# BD/BA parsing
# ---------------------------------------------------------------------------


def split_bd_ba(val: str) -> tuple[int | None, float | None]:
    """Parse '2/1' or '3 / 2.5' into (bedrooms, bathrooms)."""
    val = val.strip()
    if not val:
        return None, None
    for sep in ("/", "|"):
        if sep in val:
            parts = val.split(sep, 1)
            try:
                beds = int(parts[0].strip())
            except (ValueError, TypeError):
                beds = None
            try:
                baths = float(parts[1].strip())
            except (ValueError, TypeError):
                baths = None
            return beds, baths
    return None, None


# ---------------------------------------------------------------------------
# Property directory detection
# Used by the seeding service to identify which files to load first
# (property directories establish the manager/property source of truth).
# ---------------------------------------------------------------------------

_PROPERTY_DIRECTORY_COLUMN = frozenset({"property"})
_PROPERTY_DIRECTORY_MANAGER_COLUMNS = frozenset(
    {
        "site manager name",
        "property manager",
        "manager name",
        "assigned manager",
    }
)


def is_property_directory(columns: list[str]) -> bool:
    """True when columns look like an AppFolio property directory report."""
    lower = {c.lower().strip() for c in columns}
    return bool(lower >= _PROPERTY_DIRECTORY_COLUMN and _PROPERTY_DIRECTORY_MANAGER_COLUMNS & lower)


# ---------------------------------------------------------------------------
# Section header detection
# AppFolio rent rolls encode property addresses and occupancy section labels
# as rows with a single non-empty column. The LLM propagates these during
# extraction; this function is available for the rule-based path validation.
# ---------------------------------------------------------------------------

_SECTION_HEADER_VALUES = frozenset(
    {
        "current",
        "vacant",
        "notice",
        "past",
        "future",
        "eviction",
        "month-to-month",
        "total",
        "grand total",
        "subtotal",
        "vacant-unrented",
        "vacant-rented",
        "notice-unrented",
        "notice-rented",
    }
)


def is_section_header(row: dict[str, Any], property_key: str = "property_address") -> bool:
    """True when a row is a section header rather than a data row."""
    prop = str(row.get(property_key) or "").strip().lower()
    if prop in _SECTION_HEADER_VALUES:
        return True
    non_empty = sum(1 for v in row.values() if v is not None and str(v).strip())
    return non_empty <= 1 and not prop
