"""AppFolio report type vocabulary.

``REPORT_TYPE_DESCRIPTIONS`` are injected into the classify step prompt
so the LLM can match incoming documents against known report types.

All column maps and structural detection rules have been removed — the
LLM performs column mapping in the classify step without hardcoded lists.
"""

from __future__ import annotations

from enum import StrEnum


class AppFolioReportType(StrEnum):
    RENT_ROLL = "rent_roll"
    DELINQUENCY = "delinquency"
    LEASE_EXPIRATION = "lease_expiration"
    PROPERTY_DIRECTORY = "property_directory"
    UNKNOWN = "unknown"


# Human-readable descriptions injected into LLM classification prompts.
REPORT_TYPE_DESCRIPTIONS: dict[str, str] = {
    AppFolioReportType.RENT_ROLL: (
        "Lists every unit in the portfolio with occupancy status, lease dates, "
        "rent, and vacancy days. Has section headers like Current / Vacant-Unrented."
    ),
    AppFolioReportType.DELINQUENCY: (
        "Shows tenants with outstanding balances: amount owed, 0-30 day and 30+ day buckets, "
        "last payment date, and tenant status (Current / Notice / Evict)."
    ),
    AppFolioReportType.LEASE_EXPIRATION: (
        "Details upcoming lease expirations: move-in date, lease-end date, rent vs market rent, "
        "sqft, tenant name. Tags column often carries the property manager name."
    ),
    AppFolioReportType.PROPERTY_DIRECTORY: (
        "A listing of all properties with their assigned property manager and address. "
        "Some properties may have no manager assigned."
    ),
}
