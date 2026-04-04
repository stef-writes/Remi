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
    "title",    # ActionItem
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

_RE_AVAILABLE_AGENTS = {
    "researcher": (
        "Deep statistical analysis engine. Use for: trend analysis, regression, "
        "clustering, anomaly detection, hypothesis testing, producing research "
        "reports. Runs Python with pandas/scipy/sklearn and follows a phased "
        "protocol (LOAD > EXPLORE > HYPOTHESIZE > MODEL > VALIDATE > SYNTHESIZE)."
    ),
    "action_planner": (
        "Action item generator. Use for: analyzing a manager's portfolio data "
        "and proposing prioritized, concrete action items. Receives a JSON "
        "payload with portfolio context and returns structured action plans."
    ),
}

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

_RE_DATA_BRIDGE_HINT = (
    "Use `import remi_data` to query live platform data "
    "(properties, units, leases, maintenance, signals)."
)


def build_re_profile() -> DomainProfile:
    """Build the real estate domain profile."""
    return DomainProfile(
        name_fields=_RE_NAME_FIELDS,
        metadata_skip_patterns=_RE_METADATA_SKIP_PATTERNS,
        empty_state_label="portfolio",
        scope_entity_type="PropertyManager",
        tool_hints=dict(_RE_TOOL_HINTS),
        available_agents=dict(_RE_AVAILABLE_AGENTS),
        api_path_examples=_RE_API_PATH_EXAMPLES,
        data_bridge_hint=_RE_DATA_BRIDGE_HINT,
    )
