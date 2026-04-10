"""Ingestion rules — deterministic domain knowledge for the pipeline.

Junk filtering, address normalization, BD/BA parsing, section header detection,
type coercion (date/decimal/int), enum maps, report authority tables, and
lease tag parsing.

Column vocabulary and fuzzy header matching live in ``vocab.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from remi.application.core.models.address import Address
from remi.application.core.models.date_range import DateRange
from remi.application.core.models.enums import (
    LeaseType,
    MaintenanceStatus,
    Priority,
    RenewalStatus,
    TenantStatus,
    TradeCategory,
)

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Junk property filtering
# AppFolio internal bookkeeping entries that are not real rental properties.
# Rows like "1234 Morning Meeting" or "Auto Loan" are internal categories,
# not physical addresses.  "DO NOT USE" and "ZEROED OUT" are real addresses
# that the company has deactivated — those are handled separately as
# inactive properties, not junk.
# ---------------------------------------------------------------------------

_JUNK_PREFIXES = (
    "1234 ",
    "1234-",
    "2022 holiday",
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

_JUNK_EXACT = frozenset(
    {
        "total",
        "grand total",
        "subtotal",
        "totals",
    }
)

_JUNK_CONTAINS = frozenset(
    {
        "pto",
        "morning meeting",
        "renovation meeting",
        "staging",
        "must enter address",
        "outside project",
    }
)

# Prefixes that mark real physical properties as inactive/deactivated in
# AppFolio.  We strip the prefix, create the property, and flag its status.
_INACTIVE_PREFIXES = (
    "DO NOT USE - ",
    "DO NOT USE-",
    "DO NOT USE ",
    "ZEROED OUT - ",
    "ZEROED OUT-",
    "ZEROED OUT ",
)


def is_junk_property(address: str) -> bool:
    """True when the address is an AppFolio internal bookkeeping entry.

    Does NOT flag "DO NOT USE" or "ZEROED OUT" addresses — those are real
    properties with an inactive status marker.
    """
    lower = address.lower().strip()
    if lower in _JUNK_EXACT:
        return True
    if any(lower.startswith(p) for p in _JUNK_PREFIXES):
        return True
    if any(kw in lower for kw in _JUNK_CONTAINS):
        return True
    # Pure-numeric strings are AppFolio internal IDs or spreadsheet totals,
    # never real addresses (e.g. "28", "999", "1877").
    if re.match(r"^\d+$", lower):
        return True
    return False


def is_inactive_property(address: str) -> bool:
    """True when the raw address carries a deactivation prefix.

    The property is real but marked inactive in AppFolio.
    """
    upper = address.upper().strip()
    return any(upper.startswith(p.upper()) for p in _INACTIVE_PREFIXES)


# ---------------------------------------------------------------------------
# Address normalization
# ---------------------------------------------------------------------------

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
        remainder = address[idx + len(sep) :]
        if label and remainder.lower().startswith(label.lower()):
            return remainder.strip()
        start = idx + len(sep)

    # Fallback: if the string has multiple " - " segments and the last segment
    # starts with a digit (street number), take it — it's the canonical address.
    last_idx = address.rfind(sep)
    if last_idx > 0:
        last_part = address[last_idx + len(sep) :].strip()
        if last_part and last_part[0].isdigit():
            return last_part

    return address


def normalize_address(address: str) -> str:
    """Strip AppFolio label prefixes and deactivation markers from addresses."""
    address = _strip_appfolio_label(address)
    for prefix in _INACTIVE_PREFIXES:
        if address.upper().startswith(prefix.upper()):
            return address[len(prefix) :].strip()
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
# Manager tag validation
# AppFolio Tags columns contain a mix of real manager names and lease-level
# labels ("Section 8", "MTM", "12 Month Renewal - $25 Rent Increase").
# This guard prevents lease tags from creating fake managers.
# ---------------------------------------------------------------------------

_MANAGER_SUFFIXES = frozenset({
    "management", "mgmt", "properties", "property", "realty",
    "group", "llc", "inc", "corp", "associates",
})

_NON_MANAGER_MARKERS = frozenset({
    "section 8", "hcvp", "mtm", "ofs", "renewal", "eviction",
    "notice", "signing", "pays", "payment", "waiting", "lapsed",
    "faith", "hello", "program", "tenant", "owner", "lease",
    "addendum", "making", "possible", "month to month",
    # Report/portfolio aggregate labels — too generic to be manager names.
    # AppFolio metadata and section headers frequently contain these strings.
    "portfolio", "all properties", "all managers", "all units",
    "portfolio wide", "portfolio summary", "combined", "grand total", "subtotal",
})

# Words that commonly prefix a management suffix in a non-person context.
# "All Properties" passes the suffix check ("properties" is a suffix) but the
# first token "all" signals this is a label, not a name.
_NON_NAME_PREFIXES = frozenset({
    "all", "combined", "total", "grand", "full", "complete",
    "any", "each", "every", "other", "various", "misc",
})


def is_manager_tag(tag: str) -> bool:
    """True when a tag string plausibly names a site manager or management company.

    Rejects common AppFolio lease-level tags and report aggregate labels that
    should never create managers.

    Accept rules (checked in order):
    1. Any rejection marker is a substring → False.
    2. Last token is a management suffix AND first token is not a non-name
       prefix (e.g. "all", "total") → True.
    3. Two or more alphabetic tokens AND at least one original token starts
       with an uppercase letter (proper-noun signal) → True.
    """
    lower = tag.strip().lower()
    if not lower:
        return False

    if any(marker in lower for marker in _NON_MANAGER_MARKERS):
        return False

    tokens = lower.split()

    if tokens[-1] in _MANAGER_SUFFIXES:
        # Reject labels like "All Properties", "Combined Group"
        if tokens[0] in _NON_NAME_PREFIXES:
            return False
        return True

    alpha_tokens = [t for t in tokens if t.isalpha() and len(t) > 1]
    if len(alpha_tokens) >= 2:
        # Require at least one proper-noun indicator: an original token that
        # starts with an uppercase letter. This rejects all-lowercase report
        # labels while accepting person names like "Alex Budavich".
        original_tokens = tag.strip().split()
        if any(t and t[0].isupper() and t.isalpha() for t in original_tokens):
            return True

    return False


# ---------------------------------------------------------------------------
# Lease tag parsing — structured field extraction from AppFolio Tags column
#
# Tags like "Section 8", "90 Day Notice Clause", "12 Month Renewal" carry
# lease-level metadata that maps to existing Lease/Tenant model fields.
# is_manager_tag() already rejects these as manager names; this function
# extracts the actual information instead of discarding it.
# ---------------------------------------------------------------------------

_NOTICE_RE = re.compile(r"(\d+)\s*day\s*notice", re.IGNORECASE)
_RENEWAL_TERM_RE = re.compile(r"(\d+)\s*month\s*renewal", re.IGNORECASE)

_SUBSIDY_TAGS = frozenset({
    "section 8", "hcvp", "housing choice voucher",
    "project based voucher", "pbv", "vash", "lihtc",
})

_MTM_TAGS = frozenset({"mtm", "month to month", "m2m"})

_EVICTION_TAGS = frozenset({
    "file for eviction", "eviction", "eviction filed",
    "eviction pending", "filing",
})

_TAG_TENANT_STATUS: dict[str, TenantStatus] = {
    "file for eviction": TenantStatus.FILING,
    "eviction filed": TenantStatus.FILING,
    "eviction pending": TenantStatus.FILING,
    "eviction": TenantStatus.EVICT,
    "filing": TenantStatus.FILING,
    "notice": TenantStatus.NOTICE,
}


class LeaseTagFields:
    """Structured fields extracted from a raw tag string.

    Only non-None attributes should be applied to the target entity.
    """

    __slots__ = (
        "subsidy_program", "lease_type", "notice_days",
        "renewal_status", "renewal_term_months",
        "is_month_to_month", "tenant_status",
    )

    def __init__(self) -> None:
        self.subsidy_program: str | None = None
        self.lease_type: LeaseType | None = None
        self.notice_days: int | None = None
        self.renewal_status: RenewalStatus | None = None
        self.renewal_term_months: int | None = None
        self.is_month_to_month: bool = False
        self.tenant_status: TenantStatus | None = None

    @property
    def has_data(self) -> bool:
        return (
            self.subsidy_program is not None
            or self.lease_type is not None
            or self.notice_days is not None
            or self.renewal_status is not None
            or self.is_month_to_month
            or self.tenant_status is not None
        )

    def lease_updates(self) -> dict[str, object]:
        """Fields to merge into a Lease model_copy(update=...)."""
        out: dict[str, object] = {}
        if self.subsidy_program is not None:
            out["subsidy_program"] = self.subsidy_program
            out["lease_type"] = LeaseType.SECTION8
        if self.notice_days is not None:
            out["notice_days"] = self.notice_days
        if self.renewal_status is not None:
            out["renewal_status"] = self.renewal_status
        if self.renewal_term_months is not None:
            out["renewal_offer_term_months"] = self.renewal_term_months
        if self.is_month_to_month:
            out["is_month_to_month"] = True
            out["lease_type"] = LeaseType.MONTH_TO_MONTH
        return out


def parse_lease_tags(raw: str) -> LeaseTagFields:
    """Extract structured lease/tenant fields from a raw AppFolio tag string.

    Comma-separated segments are classified independently. Unrecognized
    segments are silently skipped — this is intentional; new tag patterns
    should be added here when discovered, not force-fit into existing fields.
    """
    result = LeaseTagFields()
    if not raw:
        return result

    segments = [s.strip() for s in raw.split(",") if s.strip()]
    for seg in segments:
        lower = seg.lower()

        if lower in _SUBSIDY_TAGS:
            result.subsidy_program = seg
            result.lease_type = LeaseType.SECTION8
            continue

        if lower in _MTM_TAGS:
            result.is_month_to_month = True
            continue

        if lower in _EVICTION_TAGS or lower in _TAG_TENANT_STATUS:
            result.tenant_status = _TAG_TENANT_STATUS.get(lower, TenantStatus.EVICT)
            continue

        m = _NOTICE_RE.search(seg)
        if m:
            result.notice_days = int(m.group(1))
            continue

        m = _RENEWAL_TERM_RE.search(seg)
        if m:
            result.renewal_term_months = int(m.group(1))
            result.renewal_status = RenewalStatus.OFFERED
            continue

    return result


# ---------------------------------------------------------------------------
# Metadata-based manager + scope extraction
# Deterministic — runs before the LLM touches the document.
# ---------------------------------------------------------------------------

_MANAGER_METADATA_KEYS = ("property_groups", "report_group", "group", "manager")


def resolve_manager_from_metadata(
    metadata: dict[str, str],
) -> tuple[str | None, str]:
    """Extract manager name and scope from parsed document metadata.

    Returns ``(manager_name, scope)`` where manager_name is the raw tag
    string (e.g. "Ryan Steen Mgmt") and scope is ``"manager_portfolio"``
    or ``"portfolio_wide"``.

    Only looks at structured metadata keys that reliably identify a
    manager (``property_groups``, ``report_group``, ``group``, ``manager``).
    Report titles and filenames are never used.
    """
    for key in _MANAGER_METADATA_KEYS:
        val = (metadata.get(key) or "").strip()
        if val and is_manager_tag(val):
            return val, "manager_portfolio"
    return None, "portfolio_wide"


# ---------------------------------------------------------------------------
# Report date extraction
# AppFolio embeds export date and optional date-range in the pre-header rows.
# We extract these to populate Document.effective_date and Document.coverage,
# which are the temporal spine for time-series queries.
# ---------------------------------------------------------------------------

# Metadata keys are already normalised to lowercase_with_underscores by the parser.
# We match on these directly rather than reconstructing the original raw line.

# "exported_on" → "02/23/2026 02:44 PM"  (time portion is ignored)
# "export_date" → same
_EXPORTED_ON_KEYS = frozenset({"exported_on", "export_date"})

# "as_of" → "03/23/2026"
_AS_OF_KEYS = frozenset({"as_of"})

# "date_range" → "Mar 2026 to Jun 2026"
_DATE_RANGE_KEYS = frozenset({"date_range"})

# Value: MM/DD/YYYY (optional trailing time is ignored)
_MDY_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")

# Value: "Mon YYYY to Mon YYYY"
_RANGE_VAL_RE = re.compile(
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})"
    r"\s+to\s+"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})",
    re.I,
)

# Filename date patterns: YYYYMMDD or YYYY-MM-DD anywhere in the name
_FILENAME_DATE_RE = re.compile(
    r"(?:^|[-_])(\d{4})[-_]?(\d{2})[-_]?(\d{2})(?:\.|$|-)"
)

_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_mdy(raw: str) -> date | None:
    """Extract and parse the first MM/DD/YYYY substring, returning None on failure."""
    m = _MDY_RE.search(raw)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%m/%d/%Y").date()
    except ValueError:
        return None


def _parse_mon_year(raw: str) -> tuple[int, int] | None:
    """Parse 'Mar 2026' → (2026, 3), returning None on failure."""
    parts = raw.strip().split()
    if len(parts) != 2:
        return None
    month = _MONTH_ABBR.get(parts[0].lower()[:3])
    try:
        year = int(parts[1])
    except ValueError:
        return None
    if month is None:
        return None
    return year, month


def _last_day_of_month(year: int, month: int) -> date:
    """Return the last calendar day of the given month."""
    import calendar
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last)


@dataclass(frozen=True)
class ReportDates:
    """Temporal metadata extracted from an AppFolio report.

    ``effective_date`` is the "as of" date — when the snapshot was taken.
    For most reports this is the export date.  For rent rolls AppFolio also
    emits an explicit "As of:" field that takes precedence.

    ``coverage`` is the closed date interval the data covers.  Only present
    on ranged reports (e.g. Lease Expiration, Maintenance History).  For
    point-in-time snapshots (delinquency, rent roll) it is None.
    """

    effective_date: date | None
    coverage: DateRange | None


def resolve_report_dates(
    metadata: dict[str, str],
    filename: str = "",
) -> ReportDates:
    """Extract the temporal spine from AppFolio report metadata + filename.

    Priority for ``effective_date``:
      1. "As of: MM/DD/YYYY"        (rent roll explicit snapshot date)
      2. "Exported On: MM/DD/YYYY"  (all other AppFolio reports)
      3. YYYYMMDD or YYYY-MM-DD in the filename
      4. None — caller should fall back to upload timestamp

    ``coverage`` is set from "Date Range: Mon YYYY to Mon YYYY" when present.
    """
    effective_date: date | None = None
    coverage: DateRange | None = None

    # Metadata keys are already lowercased + underscored by the parser.
    # "as_of" takes priority over "exported_on" (rent roll has both).
    for key, raw_val in metadata.items():
        val = (raw_val or "").strip()
        if not val:
            continue

        if key in _AS_OF_KEYS and effective_date is None:
            effective_date = _parse_mdy(val)

        elif key in _EXPORTED_ON_KEYS and effective_date is None:
            effective_date = _parse_mdy(val)

        elif key in _DATE_RANGE_KEYS and coverage is None:
            m = _RANGE_VAL_RE.search(val)
            if m:
                start_parts = _parse_mon_year(m.group(1))
                end_parts = _parse_mon_year(m.group(2))
                if start_parts and end_parts:
                    try:
                        coverage = DateRange(
                            start=date(start_parts[0], start_parts[1], 1),
                            end=_last_day_of_month(end_parts[0], end_parts[1]),
                        )
                    except ValueError:
                        _log.warning(
                            "report_date_range_invalid",
                            raw_start=m.group(1),
                            raw_end=m.group(2),
                        )

    # Re-scan: "as_of" may appear after "exported_on" in the dict — ensure
    # it wins even if exported_on was already set.
    as_of_raw = metadata.get("as_of", "").strip()
    if as_of_raw:
        parsed = _parse_mdy(as_of_raw)
        if parsed is not None:
            effective_date = parsed

    # Fallback: parse date from filename (e.g. "property_directory-20260330.xlsx")
    if effective_date is None and filename:
        fm = _FILENAME_DATE_RE.search(filename)
        if fm:
            try:
                effective_date = date(int(fm.group(1)), int(fm.group(2)), int(fm.group(3)))
            except ValueError:
                pass

    return ReportDates(effective_date=effective_date, coverage=coverage)


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


_SUMMARY_ROW_RE = re.compile(
    r"^(total|grand\s+total|subtotal|totals)$", re.I,
)

_UNITS_SUMMARY_RE = re.compile(
    r"^\d+\s+units?$", re.I,
)


def is_summary_row(row: dict[str, Any]) -> bool:
    """True when any visible field contains only a summary label like 'Total'.

    AppFolio reports append aggregate rows at section boundaries and at the
    end. These carry labels in the first text column (e.g. 'Total' in the
    Tenant Status or Property column) but their numeric columns hold sums,
    not per-entity values. They must be filtered before persistence.

    Also matches "N Units" summary rows (e.g. "136 Units") that appear
    between sections in rent roll reports.
    """
    for val in row.values():
        if val is None:
            continue
        text = str(val).strip()
        if not text:
            continue
        if _SUMMARY_ROW_RE.match(text):
            return True
        if _UNITS_SUMMARY_RE.match(text):
            return True
        return False
    return False


# ---------------------------------------------------------------------------
# Persistable entity types
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
# Report type authority — what each report type is allowed to create.
#
# If a report type is absent, unknown, or the entity type is absent from its
# set, the row is BLOCKED and not persisted.  This is the single source of
# truth for write permissions — no authority logic lives in the persisters.
#
# "enrich-only" entity types (Property in rent_roll, Unit in delinquency)
# are intentionally absent: those report types may touch existing records
# but must never create new ones.  The persister functions already guard
# individual enrich paths; this table guards the dispatch decision.
# ---------------------------------------------------------------------------

REPORT_CAN_CREATE: dict[str, frozenset[str]] = {
    "property_directory": frozenset({
        "Property", "PropertyManager", "Unit",
    }),
    "unit_directory": frozenset({
        # Unit is the primary entity. Property is allowed so that _ensure_property
        # can create the property record when unit_directory is ingested standalone
        # (without a prior property_directory). PropertyManager is excluded —
        # unit_directory manager attribution comes from the Tags column, which
        # flows through the ManagerResolver inside persist_unit, not as a top-level
        # row type.
        "Unit", "Property",
    }),
    "rent_roll": frozenset({
        "Unit", "Lease", "Tenant",
    }),
    "lease_expiration": frozenset({
        "Lease", "Tenant",
    }),
    "delinquency": frozenset({
        "BalanceObservation", "Tenant",
        # Property and Unit intentionally absent — delinquency must not
        # create phantom properties or inflate vacancy counts.
    }),
    "maintenance": frozenset({
        "MaintenanceRequest",
    }),
    "work_order": frozenset({
        "MaintenanceRequest",
    }),
    "tenant_directory": frozenset({
        "Tenant",
    }),
    "owner_directory": frozenset({
        "Owner",
    }),
    "vendor_directory": frozenset({
        "Vendor",
    }),
    "manager_directory": frozenset({
        "PropertyManager",
    }),
}

# ---------------------------------------------------------------------------
# Field authority — which fields each report type can overwrite on existing
# entities.  Non-authority fields are fill-only (enrich empty, never clobber).
# This is the confidence-merge counterpart to REPORT_CAN_CREATE above.
# ---------------------------------------------------------------------------

REPORT_FIELD_AUTHORITY: dict[str, dict[str, frozenset[str]]] = {
    "rent_roll": {
        "Unit": frozenset({"bedrooms", "bathrooms", "sqft", "market_rent", "occupancy_status", "days_vacant"}),
        "Lease": frozenset({"monthly_rent", "market_rent", "deposit", "is_month_to_month"}),
        "Tenant": frozenset({"name", "phone"}),
    },
    "delinquency": {
        "Tenant": frozenset({"status"}),
    },
    "lease_expiration": {
        "Lease": frozenset({"start_date", "end_date", "monthly_rent", "market_rent"}),
        "Tenant": frozenset({"name", "phone"}),
    },
    "property_directory": {
        "Property": frozenset({"manager_id", "address", "unit_count", "status"}),
        "PropertyManager": frozenset({"name", "email", "phone", "company", "territory"}),
    },
    "maintenance": {
        "MaintenanceRequest": frozenset({
            "status", "priority", "scheduled_date", "completed_date",
            "resolved_at", "cost", "vendor", "vendor_id",
        }),
    },
}

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
    if val is None:
        return Decimal("0")
    if isinstance(val, bool):
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


def to_decimal_or_none(val: object) -> Decimal | None:
    """Like to_decimal but returns None when the value is absent/empty,
    so callers can distinguish 'not provided' from '$0'."""
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    text = _CURRENCY_STRIP_RE.sub("", str(val).strip())
    if not text:
        return None
    m = _PARENS_RE.match(text)
    if m:
        text = f"-{m.group(1)}"
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def to_int(val: object) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Address parsing
# ---------------------------------------------------------------------------

_STREET_SUFFIXES = frozenset(
    {
        "st",
        "ave",
        "avenue",
        "blvd",
        "boulevard",
        "ct",
        "court",
        "dr",
        "drive",
        "ln",
        "lane",
        "pl",
        "place",
        "rd",
        "road",
        "sq",
        "street",
        "ter",
        "terrace",
        "way",
        "cir",
        "circle",
        "pkwy",
        "parkway",
        "hwy",
        "highway",
        "run",
        "alley",
        "aly",
    }
)

_CITY_STATE_ZIP_RE = re.compile(r",\s*([A-Za-z\s]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$")
_STATE_ZIP_RE = re.compile(r",\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$")
_TRAILING_STATE_RE = re.compile(r",\s*([A-Z]{2})\s*$")


def _split_address(raw: str) -> tuple[str, str, str, str]:
    addr = raw.strip()
    if not addr:
        return ("", "", "", "")
    m = _CITY_STATE_ZIP_RE.search(addr)
    if m:
        street = addr[: m.start()].strip().rstrip(",")
        return (street, m.group(1).strip(), m.group(2), m.group(3))
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
    m = _TRAILING_STATE_RE.search(addr)
    if m:
        street = addr[: m.start()].strip().rstrip(",")
        return (street, "", m.group(1), "")
    return (addr, "", "", "")


_HOUSE_NUMBER_ONLY_RE = re.compile(r"^[\d\-/]+$")


def property_name(address: str) -> str:
    street, city, _state, _zipcode = _split_address(address)
    if not street:
        return address.strip()
    clean = street.rstrip(",").strip()
    # When the address parser splits "1307, Mississippi Pittsburgh, PA 15216",
    # the street becomes just "1307" and "Mississippi" lands in the city field.
    # Recombine so the property gets a usable name like "1307 Mississippi".
    if _HOUSE_NUMBER_ONLY_RE.match(clean) and city:
        city_words = city.split()
        # Take words until we hit a likely city name (capitalized, not a
        # direction abbreviation like "S" or "E").
        street_parts = [clean]
        for w in city_words:
            street_parts.append(w)
            if len(w) > 2:
                break
        return " ".join(street_parts)
    return street


def parse_address(raw: str) -> Address:
    street, city, state, zipcode = _split_address(raw)
    return Address(street=street or raw.strip(), city=city, state=state, zip_code=zipcode)


# ---------------------------------------------------------------------------
# Row plausibility validation
#
# Catches obvious cross-column mapping errors before any entity is persisted.
# Returns a list of human-readable warnings. An empty list means the row is
# plausible. Callers decide whether to skip the row or persist with warnings.
#
# These checks are intentionally lenient — they flag implausible values, not
# "wrong" ones, because real-world property data is messy.
# ---------------------------------------------------------------------------

_RENT_MAX    = 50_000    # USD — anything higher is almost certainly a mismap
_UNITS_MAX   = 500       # units per property — a Pittsburgh portfolio flag
_BEDS_MAX    = 12        # bedrooms per unit
_BALANCE_MAX = 1_000_000 # delinquency balance per tenant
_DAYS_MAX    = 3_650     # days vacant (10 years) — catches date-in-numeric field


def validate_row_plausibility(row: dict[str, Any]) -> list[str]:
    """Return a list of plausibility warnings for a mapped entity row.

    Does NOT raise — callers log or surface warnings as ReviewItems.
    """
    warnings: list[str] = []
    entity = row.get("type", "unknown")

    def _num(key: str) -> float | None:
        val = row.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    # Rent fields — detect date-string-in-money or unit-count-in-rent
    for field in ("monthly_rent", "market_rent", "deposit"):
        v = _num(field)
        if v is not None:
            if v < 0:
                warnings.append(f"{entity}.{field}={v!r} is negative")
            elif v > _RENT_MAX:
                warnings.append(
                    f"{entity}.{field}={v!r} exceeds ${_RENT_MAX:,} — "
                    "possible mismap (date serial? unit count?)"
                )

    # Unit count per property — catches rent-dollar-in-unit-count
    v = _num("unit_count")
    if v is not None and v > _UNITS_MAX:
        warnings.append(
            f"Property.unit_count={v!r} exceeds {_UNITS_MAX} — "
            "possible mismap"
        )

    # Bedrooms / bathrooms per unit
    v = _num("bedrooms")
    if v is not None and (v < 0 or v > _BEDS_MAX):
        warnings.append(f"Unit.bedrooms={v!r} is out of range [0, {_BEDS_MAX}]")

    v = _num("bathrooms")
    if v is not None and (v < 0 or v > _BEDS_MAX + 4):
        warnings.append(f"Unit.bathrooms={v!r} is out of range")

    # Delinquency balance
    v = _num("balance_total")
    if v is not None and v > _BALANCE_MAX:
        warnings.append(
            f"BalanceObservation.balance_total={v!r} exceeds ${_BALANCE_MAX:,} — "
            "possible mismap"
        )

    # Days vacant — catches a serialised date integer (e.g. 44927 = Jan 2023 in Excel)
    v = _num("days_vacant")
    if v is not None and v > _DAYS_MAX:
        warnings.append(
            f"Unit.days_vacant={v!r} exceeds {_DAYS_MAX} days — "
            "possible Excel date serial number in this field"
        )

    # Tenant / property name that is purely numeric — already junk-filtered for
    # property_address, but the tenant_name field can also get a mismap.
    tenant_name = str(row.get("tenant_name") or "").strip()
    if tenant_name and tenant_name.isdigit():
        warnings.append(
            f"Tenant.tenant_name={tenant_name!r} is purely numeric — "
            "possible mismap"
        )

    return warnings

