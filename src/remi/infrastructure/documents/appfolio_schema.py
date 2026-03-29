"""AppFolio report schema definitions and type detection.

Encodes the exact column layouts from real AppFolio exports:
  - Rent Roll / Vacancy
  - Delinquency
  - Lease Expiration Detail By Month

AppFolio exports have a multi-row metadata preamble before the actual
column headers. This module handles header discovery, report type
detection, and section-aware row parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AppFolioReportType(str, Enum):
    RENT_ROLL = "rent_roll"
    DELINQUENCY = "delinquency"
    LEASE_EXPIRATION = "lease_expiration"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Column definitions per report type
# ---------------------------------------------------------------------------

# Rent Roll: Property, Unit, BD/BA, Lease From, Lease To,
#            Posted To Website, Posted To Internet, Revenue, Days Vacant, Description
RENT_ROLL_COLUMNS = {
    "Property": "property_address",
    "Unit": "unit_number",
    "BD/BA": "bd_ba",
    "Lease From": "lease_start",
    "Lease To": "lease_end",
    "Posted To Website": "posted_website",
    "Posted To Internet": "posted_internet",
    "Revenue": "revenue_flag",
    "Days Vacant": "days_vacant",
    "Description": "notes",
}

# Rent Roll section headers that indicate occupancy status
RENT_ROLL_SECTIONS = {
    "Current": "occupied",
    "Notice-Rented": "notice_rented",
    "Notice-Unrented": "notice_unrented",
    "Vacant-Rented": "vacant_rented",
    "Vacant-Unrented": "vacant_unrented",
}

# Delinquency: Tenant Status, Property, Unit, Name, Rent,
#              Amount Receivable, Delinquent Subsidy Amount, Last Payment,
#              0-30, 30+, Tags, Delinquency Notes
DELINQUENCY_COLUMNS = {
    "Tenant Status": "tenant_status",
    "Property": "property_address",
    "Unit": "unit_number",
    "Name": "tenant_name",
    "Rent": "monthly_rent",
    "Amount Receivable": "amount_owed",
    "Delinquent Subsidy Amount": "subsidy_delinquent",
    "Last Payment": "last_payment_date",
    "0-30": "balance_0_30",
    "30+": "balance_30_plus",
    "Tags": "tags",
    "Delinquency Notes": "delinquency_notes",
}

# Lease Expiration: Tags, Property, Unit, Move In, Lease Expires,
#                   Rent, Market Rent, Sqft, Tenant Name, Deposit, Phone Numbers
LEASE_EXPIRATION_COLUMNS = {
    "Tags": "tags",
    "Property": "property_address",
    "Unit": "unit_number",
    "Move In": "move_in_date",
    "Lease Expires": "lease_expires",
    "Rent": "monthly_rent",
    "Market Rent": "market_rent",
    "Sqft": "sqft",
    "Tenant Name": "tenant_name",
    "Deposit": "deposit",
    "Phone Numbers": "phone_numbers",
}

# Column fingerprints used for report type detection
_RENT_ROLL_FINGERPRINT = {"Property", "Unit", "BD/BA", "Lease From", "Lease To", "Days Vacant"}
_DELINQUENCY_FINGERPRINT = {"Tenant Status", "Property", "Unit", "Name", "Amount Receivable", "0-30", "30+"}
_LEASE_EXPIRATION_FINGERPRINT = {"Tags", "Property", "Unit", "Move In", "Lease Expires", "Market Rent", "Sqft"}


# ---------------------------------------------------------------------------
# Parsed row dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RentRollRow:
    property_address: str
    property_name: str        # short form: "1018 Woodbourne Avenue"
    unit_number: str | None
    occupancy_status: str     # occupied / notice_rented / notice_unrented / vacant_rented / vacant_unrented
    bedrooms: int | None
    bathrooms: float | None
    lease_start: datetime | None
    lease_end: datetime | None
    posted_website: bool
    posted_internet: bool
    days_vacant: int | None
    notes: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DelinquencyRow:
    tenant_status: str        # Current / Notice / Evict
    property_address: str
    property_name: str
    unit_number: str | None
    tenant_name: str
    monthly_rent: float
    amount_owed: float
    subsidy_delinquent: float
    last_payment_date: datetime | None
    balance_0_30: float
    balance_30_plus: float
    tags: str | None
    delinquency_notes: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LeaseExpirationRow:
    tags: str | None          # e.g. "Jake Kraus Management" (manager tag)
    property_address: str
    property_name: str
    unit_number: str | None
    move_in_date: datetime | None
    lease_expires: datetime | None
    monthly_rent: float
    market_rent: float | None
    sqft: int | None
    tenant_name: str
    deposit: float
    phone_numbers: str | None
    is_month_to_month: bool
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detection and parsing
# ---------------------------------------------------------------------------

def detect_report_type(column_names: list[str]) -> AppFolioReportType:
    """Identify which AppFolio report type based on column names."""
    col_set = set(column_names)
    if _DELINQUENCY_FINGERPRINT.issubset(col_set):
        return AppFolioReportType.DELINQUENCY
    if _LEASE_EXPIRATION_FINGERPRINT.issubset(col_set):
        return AppFolioReportType.LEASE_EXPIRATION
    if _RENT_ROLL_FINGERPRINT.issubset(col_set):
        return AppFolioReportType.RENT_ROLL
    return AppFolioReportType.UNKNOWN


def parse_property_name(full_address: str) -> str:
    """Extract short property name from AppFolio's 'Name - Full Address' format.

    AppFolio encodes property addresses as either:
      '1018 Woodbourne Avenue - 1018 Woodbourne Avenue Pittsburgh, PA 15226'
    or just:
      '142 S. 19th Street Pittsburgh, PA 15203'

    Returns the part before the dash, or the full string if no dash found.
    """
    if not full_address:
        return full_address
    if " - " in full_address:
        return full_address.split(" - ")[0].strip()
    # Strip trailing city/state/zip if no dash separator
    # e.g. "142 S. 19th Street Pittsburgh, PA 15203" -> "142 S. 19th Street"
    parts = full_address.split(",")
    if len(parts) >= 2:
        # Remove the last two comma-separated pieces (city state zip, state zip)
        street_part = parts[0].strip()
        # Also strip city if it's embedded in the street part (no comma before city)
        # Heuristic: city starts after last digit in zip-less string
        return street_part
    return full_address.strip()


def parse_bd_ba(bd_ba: str | None) -> tuple[int | None, float | None]:
    """Parse AppFolio BD/BA field like '3/1.00', '2/2.50', '--/--'.

    Returns (bedrooms, bathrooms).
    """
    if not bd_ba or bd_ba == "--/--":
        return None, None
    try:
        parts = str(bd_ba).split("/")
        beds = int(parts[0]) if parts[0].strip() != "--" else None
        baths = float(parts[1]) if len(parts) > 1 and parts[1].strip() != "--" else None
        return beds, baths
    except (ValueError, IndexError):
        return None, None


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _to_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return None


def _to_bool(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("yes", "true", "1")


# ---------------------------------------------------------------------------
# Section-aware Rent Roll parsing
# ---------------------------------------------------------------------------

def parse_rent_roll_rows(
    raw_rows: list[dict[str, Any]],
) -> list[RentRollRow]:
    """Parse all data rows from a rent roll document, tracking occupancy sections.

    The rent roll has section header rows (e.g. {'Property': 'Current', ...})
    that set the occupancy_status for all subsequent rows until the next section.
    Count summary rows (e.g. {'Unit': '136 Units'}) are skipped.
    """
    results: list[RentRollRow] = []
    current_section = "occupied"

    for row in raw_rows:
        property_val = row.get("Property") or row.get("property_address") or ""
        unit_val = row.get("Unit") or row.get("unit_number")

        # Section header detection: Property col contains section name, all others empty/None
        if str(property_val).strip() in RENT_ROLL_SECTIONS:
            current_section = RENT_ROLL_SECTIONS[str(property_val).strip()]
            continue

        # Count summary row: Unit col contains "N Units", Property is None
        if property_val is None and unit_val and str(unit_val).endswith("Units"):
            continue
        if not property_val or str(property_val).strip() == "":
            continue

        beds, baths = parse_bd_ba(row.get("BD/BA") or row.get("bd_ba"))

        results.append(RentRollRow(
            property_address=str(property_val),
            property_name=parse_property_name(str(property_val)),
            unit_number=str(unit_val).strip() if unit_val else None,
            occupancy_status=current_section,
            bedrooms=beds,
            bathrooms=baths,
            lease_start=_to_datetime(row.get("Lease From") or row.get("lease_start")),
            lease_end=_to_datetime(row.get("Lease To") or row.get("lease_end")),
            posted_website=_to_bool(row.get("Posted To Website") or row.get("posted_website")),
            posted_internet=_to_bool(row.get("Posted To Internet") or row.get("posted_internet")),
            days_vacant=_to_int(row.get("Days Vacant") or row.get("days_vacant")),
            notes=str(row.get("Description") or row.get("notes") or "").strip() or None,
            raw=row,
        ))

    return results


def parse_delinquency_rows(
    raw_rows: list[dict[str, Any]],
) -> list[DelinquencyRow]:
    """Parse all data rows from a delinquency document."""
    results: list[DelinquencyRow] = []

    for row in raw_rows:
        property_val = row.get("Property") or row.get("property_address") or ""
        if not property_val or str(property_val).strip() == "":
            continue

        unit_val = row.get("Unit") or row.get("unit_number")
        tenant_name = str(row.get("Name") or row.get("tenant_name") or "").strip()
        if not tenant_name:
            continue

        results.append(DelinquencyRow(
            tenant_status=str(row.get("Tenant Status") or row.get("tenant_status") or "").strip(),
            property_address=str(property_val),
            property_name=parse_property_name(str(property_val)),
            unit_number=str(unit_val).strip() if unit_val else None,
            tenant_name=tenant_name,
            monthly_rent=_to_float(row.get("Rent") or row.get("monthly_rent")),
            amount_owed=_to_float(row.get("Amount Receivable") or row.get("amount_owed")),
            subsidy_delinquent=_to_float(row.get("Delinquent Subsidy Amount") or row.get("subsidy_delinquent")),
            last_payment_date=_to_datetime(row.get("Last Payment") or row.get("last_payment_date")),
            balance_0_30=_to_float(row.get("0-30") or row.get("balance_0_30")),
            balance_30_plus=_to_float(row.get("30+") or row.get("balance_30_plus")),
            tags=str(row.get("Tags") or row.get("tags") or "").strip() or None,
            delinquency_notes=str(row.get("Delinquency Notes") or row.get("delinquency_notes") or "").strip() or None,
            raw=row,
        ))

    return results


def parse_lease_expiration_rows(
    raw_rows: list[dict[str, Any]],
) -> list[LeaseExpirationRow]:
    """Parse all data rows from a lease expiration document.

    The first row may have 'Month-To-Month' in the Tags column as a section label.
    Rows with no property or tenant are skipped.
    """
    results: list[LeaseExpirationRow] = []
    current_is_mtm = False

    for row in raw_rows:
        tags_val = str(row.get("Tags") or row.get("tags") or "").strip()
        property_val = row.get("Property") or row.get("property_address") or ""
        tenant_val = str(row.get("Tenant Name") or row.get("tenant_name") or "").strip()

        is_section_header = not str(property_val).strip() and not tenant_val
        if is_section_header:
            if tags_val == "Month-To-Month":
                current_is_mtm = True
            else:
                current_is_mtm = False
            continue

        if not str(property_val).strip() or not tenant_val:
            continue

        unit_val = row.get("Unit") or row.get("unit_number")

        results.append(LeaseExpirationRow(
            tags=tags_val or None,
            property_address=str(property_val),
            property_name=parse_property_name(str(property_val)),
            unit_number=str(unit_val).strip() if unit_val else None,
            move_in_date=_to_datetime(row.get("Move In") or row.get("move_in_date")),
            lease_expires=_to_datetime(row.get("Lease Expires") or row.get("lease_expires")),
            monthly_rent=_to_float(row.get("Rent") or row.get("monthly_rent")),
            market_rent=_to_float(row.get("Market Rent") or row.get("market_rent")) or None,
            sqft=_to_int(row.get("Sqft") or row.get("sqft")),
            tenant_name=tenant_val,
            deposit=_to_float(row.get("Deposit") or row.get("deposit")),
            phone_numbers=str(row.get("Phone Numbers") or row.get("phone_numbers") or "").strip() or None,
            is_month_to_month=current_is_mtm or (row.get("Lease Expires") is None),
            raw=row,
        ))

    return results
