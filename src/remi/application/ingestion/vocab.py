"""Column vocabulary and report profile detection for AppFolio PM reports.

Traditional ETL approach: normalize the header, look it up in a vocabulary dict,
check which profile's required columns are all present. No scoring math.

Extending this module:
  - New column variant → add an entry to ``VOCAB``.
  - New report type → add a ``Profile`` to ``PROFILES``.
  - New install quirk → add entries under the existing canonical field.

The LLM is only called when no profile matches. That should be rare for
AppFolio; each new format encountered gets added here, not to the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Vocabulary — raw (lowercased) header → canonical field name
#
# One entry per known variant. Order doesn't matter. New variants go here,
# never in the LLM prompt.
# ---------------------------------------------------------------------------

VOCAB: dict[str, str] = {
    # ── Property address ──────────────────────────────────────────────────
    "property":                  "property_address",
    "property address":          "property_address",
    "property name":             "property_address",
    "address":                   "property_address",
    "location":                  "property_address",
    "building":                  "property_address",
    "building address":          "property_address",
    "street address":            "property_address",
    "prop address":              "property_address",

    # ── Unit ─────────────────────────────────────────────────────────────
    "unit":                      "unit_number",
    "unit number":               "unit_number",
    "unit #":                    "unit_number",
    "unit no":                   "unit_number",
    "unit no.":                  "unit_number",
    "unit id":                   "unit_number",
    "apt":                       "unit_number",
    "apt #":                     "unit_number",
    "apartment":                 "unit_number",
    "apartment number":          "unit_number",
    "suite":                     "unit_number",

    # ── Beds / baths ─────────────────────────────────────────────────────
    "bd/ba":                     "_bd_ba",
    "bed/bath":                  "_bd_ba",
    "beds/baths":                "_bd_ba",
    "bd / ba":                   "_bd_ba",
    "bed / bath":                "_bd_ba",
    "beds / baths":              "_bd_ba",
    "bedrooms/bathrooms":        "_bd_ba",
    "br/ba":                     "_bd_ba",
    "bedrooms":                  "bedrooms",
    "beds":                      "bedrooms",
    "bd":                        "bedrooms",
    "bathrooms":                 "bathrooms",
    "baths":                     "bathrooms",
    "ba":                        "bathrooms",

    # ── Unit count (property directory) ──────────────────────────────────
    "units":                     "_unit_count",
    "unit count":                "_unit_count",
    "# units":                   "_unit_count",
    "#units":                    "_unit_count",
    "no. of units":              "_unit_count",
    "number of units":           "_unit_count",
    "total units":               "_unit_count",
    "num units":                 "_unit_count",

    # ── AppFolio tags ────────────────────────────────────────────────────
    "tags":                      "_manager_tag",
    "tag":                       "_manager_tag",
    "labels":                    "_manager_tag",
    "property group":            "_manager_tag",
    "property groups":           "_manager_tag",
    "group":                     "_manager_tag",
    "groups":                    "_manager_tag",

    # ── Tenant / resident ────────────────────────────────────────────────
    "tenant":                    "tenant_name",
    "tenant name":               "tenant_name",
    "resident":                  "tenant_name",
    "resident name":             "tenant_name",
    "tenants":                   "tenant_name",
    "residents":                 "tenant_name",
    "renter":                    "tenant_name",
    "renter name":               "tenant_name",
    "lessee":                    "tenant_name",
    "occupant":                  "tenant_name",
    "occupant name":             "tenant_name",

    # ── Manager / site manager ───────────────────────────────────────────
    "site manager name":         "site_manager_name",
    "site manager":              "site_manager_name",
    "property manager":          "site_manager_name",
    "manager name":              "site_manager_name",
    "assigned manager":          "site_manager_name",
    "managed by":                "site_manager_name",
    "pm":                        "site_manager_name",
    # bare "manager" and bare "name" are ambiguous — resolved by profile below

    # ── Lease dates ───────────────────────────────────────────────────────
    "lease from":                "start_date",
    "lease start":               "start_date",
    "start date":                "start_date",
    "move in":                   "start_date",
    "move in date":              "start_date",
    "move-in":                   "start_date",
    "move-in date":              "start_date",
    "tenancy start":             "start_date",
    "commencement":              "start_date",
    "lease begin":               "start_date",
    "lease to":                  "lease_expires",
    "lease end":                 "lease_expires",
    "end date":                  "lease_expires",
    "lease expires":             "lease_expires",
    "lease expiration":          "lease_expires",
    "expiration":                "lease_expires",
    "expiration date":           "lease_expires",
    "expires":                   "lease_expires",
    "expiry":                    "lease_expires",
    "lease expiry":              "lease_expires",
    "move out":                  "lease_expires",
    "move out date":             "lease_expires",
    "move-out":                  "lease_expires",
    "move-out date":             "lease_expires",
    "termination date":          "lease_expires",
    "lease termination":         "lease_expires",

    # ── Rent / financials ─────────────────────────────────────────────────
    "rent":                      "monthly_rent",
    "monthly rent":              "monthly_rent",
    "current rent":              "monthly_rent",
    "monthly charge":            "monthly_rent",
    "charge":                    "monthly_rent",
    "charges":                   "monthly_rent",
    "contract rent":             "monthly_rent",
    "lease rent":                "monthly_rent",
    "actual rent":               "monthly_rent",
    "rent amount":               "monthly_rent",
    "market rent":               "market_rent",
    "market":                    "market_rent",
    "market rate":               "market_rent",
    "list rent":                 "market_rent",
    "asking rent":               "market_rent",
    "advertised rent":           "market_rent",
    # Rent roll "Revenue" column = asking/market rate for vacant units;
    # occupied rows leave it blank so it safely falls through to market_rent.
    "revenue":                   "market_rent",
    "deposit":                   "deposit",
    "security deposit":          "deposit",
    "sec dep":                   "deposit",
    "security":                  "deposit",
    "sec deposit":               "deposit",

    # ── Sqft ─────────────────────────────────────────────────────────────
    "sqft":                      "sqft",
    "sq ft":                     "sqft",
    "square feet":               "sqft",
    "square footage":            "sqft",
    "area":                      "sqft",
    "size":                      "sqft",
    "unit size":                 "sqft",

    # ── Vacancy ───────────────────────────────────────────────────────────
    "days vacant":               "days_vacant",
    "vacancy days":              "days_vacant",
    "days on market":            "days_vacant",
    "dom":                       "days_vacant",

    # ── Tenant status ─────────────────────────────────────────────────────
    "tenant status":             "tenant_status",
    "account status":            "tenant_status",
    "resident status":           "tenant_status",
    "occupancy status":          "tenant_status",
    "occupancy":                 "tenant_status",
    "status":                    "tenant_status",

    # ── Balance / delinquency ─────────────────────────────────────────────
    "balance":                   "balance_total",
    "balance owed":              "balance_total",
    "balance due":               "balance_total",
    "total balance":             "balance_total",
    "total owed":                "balance_total",
    "amount owed":               "balance_total",
    "total due":                 "balance_total",
    "amount due":                "balance_total",
    "total receivable":          "balance_total",
    "amount receivable":         "balance_total",
    "outstanding balance":       "balance_total",
    "balance total":             "balance_total",
    "0-30":                      "balance_0_30",
    "0-30 days":                 "balance_0_30",
    "0 - 30":                    "balance_0_30",
    "current balance":           "balance_0_30",
    "under 30":                  "balance_0_30",
    "30+":                       "balance_30_plus",
    "30+ days":                  "balance_30_plus",
    "30-60":                     "balance_30_plus",
    "30 - 60":                   "balance_30_plus",
    "31-60":                     "balance_30_plus",
    "31 - 60":                   "balance_30_plus",
    "60+":                       "balance_30_plus",
    "60-90":                     "balance_30_plus",
    "60 - 90":                   "balance_30_plus",
    "90+":                       "balance_30_plus",
    "90 - 120":                  "balance_30_plus",
    "120+":                      "balance_30_plus",
    "over 30":                   "balance_30_plus",
    "over 30 days":              "balance_30_plus",
    "past 30":                   "balance_30_plus",
    "last payment":              "last_payment_date",
    "last payment date":         "last_payment_date",
    "last paid":                 "last_payment_date",
    "last paid date":            "last_payment_date",
    "payment date":              "last_payment_date",
    "date last paid":            "last_payment_date",
    "delinquency notes":         "delinquency_notes",
    "delinquent notes":          "delinquency_notes",
    "notes":                     "delinquency_notes",
    "note":                      "delinquency_notes",
    "comments":                  "delinquency_notes",
    "comment":                   "delinquency_notes",
    "delinquent subsidy amount": "_delinquent_subsidy",
    "subsidy amount":            "_delinquent_subsidy",

    # ── Maintenance ───────────────────────────────────────────────────────
    "title":                     "title",
    "work order":                "title",
    "work order #":              "title",
    "work order title":          "title",
    "description":               "description",
    "issue":                     "description",
    "problem":                   "description",
    "category":                  "category",
    "trade":                     "category",
    "maintenance type":          "category",
    "maintenance category":      "category",
    "priority":                  "priority",
    "urgency":                   "priority",
    "scheduled date":            "scheduled_date",
    "scheduled":                 "scheduled_date",
    "target date":               "scheduled_date",
    "due date":                  "scheduled_date",
    "completed date":            "completed_date",
    "completed on":              "completed_date",
    "completed":                 "completed_date",
    "completion date":           "completed_date",
    "finished date":             "completed_date",
    "closed date":               "completed_date",
    "cost":                      "cost",
    "total cost":                "cost",
    "expense":                   "cost",
    "invoice amount":            "cost",
    "vendor":                    "vendor",
    "vendor name":               "vendor",
    "assigned to":               "vendor",
    "technician":                "vendor",
    "contractor":                "vendor",
    "assigned vendor":           "vendor",

    # ── Contact ───────────────────────────────────────────────────────────
    "phone":                     "phone",
    "phone number":              "phone",
    "phone numbers":             "phone",
    "contact":                   "phone",
    "contact phone":             "phone",
    "cell":                      "phone",
    "mobile":                    "phone",
    "telephone":                 "phone",
    "contact number":            "phone",
    "email":                     "email",
    "email address":             "email",
    "e-mail":                    "email",
    "e mail":                    "email",

    # ── Company ───────────────────────────────────────────────────────────
    "company":                   "company",
    "company name":              "company",

    # ── Month-to-month ────────────────────────────────────────────────────
    "m2m":                       "is_month_to_month",
    "mtm":                       "is_month_to_month",
    "month to month":            "is_month_to_month",
    "month-to-month":            "is_month_to_month",
}

# Headers that mean different things depending on report type.
# Stored separately; resolved after profile detection.
_AMBIGUOUS: dict[str, str] = {
    "name":    "_name_ambiguous",
    "manager": "_manager_ambiguous",
}

_VOCAB_LOWER: dict[str, str] = {k.lower(): v for k, v in VOCAB.items()}
_VOCAB_LOWER.update({k.lower(): v for k, v in _AMBIGUOUS.items()})


# ---------------------------------------------------------------------------
# Regex fallback — patterns too dynamic for a flat dict
# ---------------------------------------------------------------------------

_AGING_RE   = re.compile(r"^(\d+)\s*[-–]\s*\d+(?:\s*days?)?$|^(\d+)\s*\+(?:\s*days?)?$", re.I)
_BD_BA_RE   = re.compile(r"^b[de]d?\s*/\s*ba", re.I)
_LEASE_FROM = re.compile(r"lease.*(from|start|begin|commence)", re.I)
_LEASE_TO   = re.compile(r"lease.*(to|end|expir|terminat)", re.I)
_MARKET_RE  = re.compile(r"(market|list|ask(?:ing)?)\s+rent", re.I)
_RENT_RE    = re.compile(r"(current|monthly|charg|contract|actual)\s+rent", re.I)


def _fuzzy(raw: str) -> str | None:
    if _BD_BA_RE.match(raw):
        return "_bd_ba"
    if _LEASE_FROM.search(raw):
        return "start_date"
    if _LEASE_TO.search(raw):
        return "lease_expires"
    if _MARKET_RE.search(raw):
        return "market_rent"
    if _RENT_RE.search(raw):
        return "monthly_rent"
    m = _AGING_RE.match(raw)
    if m:
        lo = int(m.group(1) or m.group(2) or 0)
        return "balance_0_30" if lo == 0 else "balance_30_plus"
    return None


def _lookup(header: str) -> str | None:
    """Three-pass lookup: exact lowercase → strip-punctuation → regex."""
    lower = header.strip().lower()
    hit = _VOCAB_LOWER.get(lower)
    if hit:
        return hit
    # Collapse punctuation/whitespace variants ("e-mail" → "e mail")
    norm = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", lower)).strip()
    hit = _VOCAB_LOWER.get(norm)
    if hit:
        return hit
    return _fuzzy(lower)


_SNAKE = re.compile(r"[^a-z0-9]+")


def _private(header: str) -> str:
    return "_" + _SNAKE.sub("_", header.lower()).strip("_")


# ---------------------------------------------------------------------------
# Report profiles — set-based detection
#
# A profile matches when ALL of its ``required`` canonical fields are present
# in the recognized columns. When multiple profiles match, the one with more
# required fields wins (more specific). No floats, no scoring.
#
# ``ambiguous_as``: how to resolve context-dependent fields ("name", "manager")
#                   once this profile is confirmed.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Profile:
    report_type: str
    entity_type: str
    required: frozenset[str]            # ALL must be present to match
    ambiguous_as: dict[str, str] = field(default_factory=dict)


PROFILES: list[Profile] = [
    Profile(
        report_type="property_directory",
        entity_type="PropertyManager",
        required=frozenset({"site_manager_name", "_unit_count"}),
        ambiguous_as={"_name_ambiguous": "site_manager_name",
                      "_manager_ambiguous": "site_manager_name"},
    ),
    Profile(
        report_type="delinquency",
        entity_type="BalanceObservation",
        required=frozenset({"balance_total", "balance_0_30"}),
        ambiguous_as={"_name_ambiguous": "tenant_name",
                      "_manager_ambiguous": "site_manager_name"},
    ),
    Profile(
        report_type="lease_expiration",
        entity_type="Lease",
        required=frozenset({"lease_expires", "tenant_name"}),
        ambiguous_as={"_name_ambiguous": "tenant_name",
                      "_manager_ambiguous": "site_manager_name"},
    ),
    Profile(
        report_type="rent_roll",
        entity_type="Unit",
        required=frozenset({"_bd_ba", "days_vacant"}),
        ambiguous_as={"_name_ambiguous": "tenant_name",
                      "_manager_ambiguous": "site_manager_name"},
    ),
    Profile(
        report_type="rent_roll",        # alternate: rent roll without days_vacant
        entity_type="Unit",
        required=frozenset({"_bd_ba", "lease_expires", "property_address"}),
        ambiguous_as={"_name_ambiguous": "tenant_name",
                      "_manager_ambiguous": "site_manager_name"},
    ),
    Profile(
        report_type="maintenance",
        entity_type="MaintenanceRequest",
        required=frozenset({"scheduled_date", "completed_date"}),
        ambiguous_as={"_name_ambiguous": "tenant_name"},
    ),
    Profile(
        report_type="tenant_directory",
        entity_type="Tenant",
        required=frozenset({"tenant_name", "email", "phone"}),
        ambiguous_as={"_name_ambiguous": "tenant_name"},
    ),
    Profile(
        report_type="owner_directory",
        entity_type="Owner",
        required=frozenset({"email", "company"}),
        ambiguous_as={"_name_ambiguous": "owner_name"},
    ),
    Profile(
        report_type="vendor_directory",
        entity_type="Vendor",
        required=frozenset({"vendor", "category"}),
        ambiguous_as={"_name_ambiguous": "vendor"},
    ),
]


def _detect(field_set: set[str]) -> Profile | None:
    """Return the most-specific matching profile, or None."""
    matches = [p for p in PROFILES if p.required.issubset(field_set)]
    if not matches:
        return None
    return max(matches, key=lambda p: len(p.required))


# ---------------------------------------------------------------------------
# Result and main entry point
# ---------------------------------------------------------------------------

@dataclass
class VocabMatch:
    column_map: dict[str, str]      # raw_header → canonical_field
    report_type: str
    primary_entity_type: str
    unrecognized: list[str]         # headers that matched nothing in VOCAB
    review_notes: list[str]         # surfaced to the human review queue
    should_proceed: bool            # True → skip LLM step


def match_columns(headers: list[str]) -> VocabMatch:
    """Map raw column headers to canonical fields and detect report type.

    Returns a :class:`VocabMatch`. ``should_proceed=True`` means the
    column map and report type are known — the LLM step is skipped.

    Detection is set-membership: a profile matches when every one of its
    required fields is present in the recognized columns. No probabilities.
    """
    raw_to_field: dict[str, str] = {}
    unrecognized: list[str] = []

    for header in headers:
        field = _lookup(header)
        if field is not None:
            raw_to_field[header] = field
        else:
            unrecognized.append(header)
            raw_to_field[header] = _private(header)

    field_set = set(raw_to_field.values())
    profile = _detect(field_set)
    review_notes: list[str] = []

    if profile is None:
        if unrecognized:
            review_notes.append(
                f"Unrecognized columns: {unrecognized}"
            )
        review_notes.append("No report profile matched — LLM required.")
        return VocabMatch(
            column_map=raw_to_field,
            report_type="unknown",
            primary_entity_type="",
            unrecognized=unrecognized,
            review_notes=review_notes,
            should_proceed=False,
        )

    # Resolve ambiguous headers using the matched profile.
    final_map = {
        h: profile.ambiguous_as.get(f, f)
        for h, f in raw_to_field.items()
    }

    if unrecognized:
        review_notes.append(
            f"Unrecognized columns (add to VOCAB when meaning is known): {unrecognized}"
        )

    # Flag collisions — two raw headers mapped to the same canonical field.
    field_sources: dict[str, list[str]] = {}
    for h, f in final_map.items():
        if not f.startswith("_"):
            field_sources.setdefault(f, []).append(h)
    for f, sources in field_sources.items():
        if len(sources) > 1:
            review_notes.append(
                f"Multiple columns map to '{f}': {sources}"
            )

    return VocabMatch(
        column_map=final_map,
        report_type=profile.report_type,
        primary_entity_type=profile.entity_type,
        unrecognized=unrecognized,
        review_notes=review_notes,
        should_proceed=True,
    )
