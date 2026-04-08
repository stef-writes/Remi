"""Real estate domain profile — declares how agent/ should operate on RE data.

This is the single place where all RE-specific operational constants live.
The container calls ``build_re_profile()`` and passes the result to agent/
consumers through their constructor parameters.
"""

from __future__ import annotations

from remi.agent.profile import DomainProfile

_RE_NAME_FIELDS = (
    "name",
    "tenant_name",
    "property_name",
    "manager_name",
    "title",  # ActionItem
    "content",  # Note (short content snippets)
)

_RE_METADATA_SKIP_PATTERNS = (
    r"properties:",
    r"units:",
    r"property\s+groups",
    r"bedrooms",
    r"bathrooms",
    r"amenities",
    r"appliances",
    r"balance:",
    r"amount\s+owed",
)

_RE_TOOL_HINTS = {
    "semantic_search": (
        "Finds tenants, units, properties, maintenance requests, and individual "
        "rows from uploaded documents whose text is semantically similar to your "
        "query. Use this for fuzzy lookups ('problem tenants', 'mold issues', "
        "'that building on Ella Street', 'overdue rent on unit 4B') where exact "
        "filters won't work. DocumentRow results include the original report row "
        "as text plus metadata with document_id, filename, report_type, and "
        "row_index."
    ),
    "semantic_search:entity_type": (
        "Filter by type: Tenant, Unit, Property, MaintenanceRequest, ActionItem, Note, DocumentRow"
    ),
}

_RE_API_PATH_EXAMPLES = (
    "Examples:\n"
    "  GET /api/v1/managers \u2014 list managers\n"
    "  POST /api/v1/actions \u2014 create action item\n"
    "  POST /api/v1/signals/infer \u2014 trigger signal inference\n"
    "  GET /api/v1/ontology/search?object_type=Property \u2014 ontology query"
)

_RE_SECTION_LABELS = frozenset({
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
})


def build_re_profile() -> DomainProfile:
    """Build the real estate domain profile."""
    return DomainProfile(
        name_fields=_RE_NAME_FIELDS,
        metadata_skip_patterns=_RE_METADATA_SKIP_PATTERNS,
        empty_state_label="data",
        scope_entity_type="PropertyManager",
        tool_hints=dict(_RE_TOOL_HINTS),
        api_path_examples=_RE_API_PATH_EXAMPLES,
        section_labels=_RE_SECTION_LABELS,
    )
