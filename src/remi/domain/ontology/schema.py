"""REMI knowledge graph schema — type registry, link types, and prompt helpers.

Entity type definitions are **derived** from the Pydantic models in
``domain.portfolio.models`` via ``agent.graph.introspect``.  This module
owns the RE-specific registry (which models to introspect, descriptions,
plural names), the structural and operational link types, and the
``entity_schemas_for_prompt`` entry point.

KG-only types that have no Pydantic model (e.g. ``Note``) are declared
as supplemental ``ObjectTypeDef`` instances here.

Seeding the knowledge graph is in ``domain.ontology.seed``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from remi.agent.graph.introspect import (
    pydantic_to_type_defs,
    schemas_for_prompt,
)
from remi.agent.graph.types import (
    KnowledgeProvenance,
    LinkTypeDef,
    ObjectTypeDef,
    PropertyDef,
)
from remi.domain.portfolio.models import (
    ActionItem,
    Lease,
    MaintenanceRequest,
    Owner,
    Portfolio,
    Property,
    PropertyManager,
    Tenant,
    Unit,
    Vendor,
)
from remi.types.paths import DOMAIN_YAML_PATH

# ---------------------------------------------------------------------------
# Model registry — the single source of truth for entity schemas.
# Each entry: (PydanticModel, description) or (PydanticModel, description, plural_name)
# ---------------------------------------------------------------------------

_MODEL_REGISTRY: list[
    tuple[type, str] | tuple[type, str, str]
] = [
    # Oversight
    (Owner, "The legal entity that owns a property asset", "Owners"),
    (PropertyManager, "A property manager overseeing one or more portfolios", "PropertyManagers"),
    (Portfolio, "A collection of properties managed together", "Portfolios"),
    # Assets
    (Property, "A real estate property (building or complex)", "Properties"),
    (Unit, "A rentable unit within a property", "Units"),
    # Leasing
    (Lease, "A lease agreement for a unit", "Leases"),
    (Tenant, "A person or entity leasing a unit", "Tenants"),
    # Operations
    (Vendor, "A service provider contracted for maintenance, repairs, or renovations", "Vendors"),
    (MaintenanceRequest, "A maintenance work order for a unit", "MaintenanceRequests"),
    # Tracking
    (
        ActionItem,
        "A director-created action item for tracking follow-ups on managers, properties, or tenants",
        "ActionItems",
    ),
]

# Derived at import time — stays in sync with models.py automatically.
_CORE_TYPE_DEFS: list[ObjectTypeDef] = pydantic_to_type_defs(_MODEL_REGISTRY)

# ---------------------------------------------------------------------------
# KG-only supplemental types (no Pydantic model)
# ---------------------------------------------------------------------------

_SUPPLEMENTAL_TYPES: list[ObjectTypeDef] = [
    ObjectTypeDef(
        name="Note",
        plural_name="Notes",
        description=(
            "An observation or note attached to any entity"
            " — from the director, AI, or ingested reports"
        ),
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="content", data_type="string", required=True),
            PropertyDef(name="entity_type", data_type="string"),
            PropertyDef(name="entity_id", data_type="string"),
            PropertyDef(
                name="provenance",
                data_type="enum",
                enum_values=["user_stated", "data_derived", "inferred"],
            ),
            PropertyDef(name="source_doc", data_type="string"),
            PropertyDef(name="created_by", data_type="string"),
        ),
    ),
]

_ALL_TYPE_DEFS: list[ObjectTypeDef] = _CORE_TYPE_DEFS + _SUPPLEMENTAL_TYPES

# ---------------------------------------------------------------------------
# Link types — structural (domain model relationships)
# ---------------------------------------------------------------------------

_STRUCTURAL_LINKS: list[LinkTypeDef] = [
    LinkTypeDef(
        name="BELONGS_TO",
        source_type="Unit",
        target_type="Property",
        cardinality="many_to_one",
        description="Unit is part of a property",
    ),
    LinkTypeDef(
        name="IN_PORTFOLIO",
        source_type="Property",
        target_type="Portfolio",
        cardinality="many_to_one",
        description="Property belongs to a portfolio",
    ),
    LinkTypeDef(
        name="MANAGED_BY",
        source_type="Property",
        target_type="PropertyManager",
        cardinality="many_to_one",
        description="Property is managed by",
    ),
    LinkTypeDef(
        name="COVERS",
        source_type="Lease",
        target_type="Unit",
        cardinality="many_to_one",
        description="Lease covers a unit",
    ),
    LinkTypeDef(
        name="SIGNED_BY",
        source_type="Lease",
        target_type="Tenant",
        cardinality="many_to_one",
        description="Lease signed by tenant",
    ),
    LinkTypeDef(
        name="AFFECTS",
        source_type="MaintenanceRequest",
        target_type="Unit",
        cardinality="many_to_one",
        description="Work order affects a unit",
    ),
    LinkTypeDef(
        name="OWNED_BY",
        source_type="Property",
        target_type="Owner",
        cardinality="many_to_one",
        description="Property is legally owned by",
    ),
    LinkTypeDef(
        name="SERVICED_BY",
        source_type="MaintenanceRequest",
        target_type="Vendor",
        cardinality="many_to_one",
        description="Work order is assigned to a vendor",
    ),
    LinkTypeDef(
        name="RENEWED_FROM",
        source_type="Lease",
        target_type="Lease",
        cardinality="many_to_one",
        description="Lease is a renewal of a prior lease",
    ),
    LinkTypeDef(
        name="HAS_NOTE",
        source_type="*",
        target_type="Note",
        description="Entity has an attached note or observation",
    ),
]

_OPERATIONAL_LINKS: list[LinkTypeDef] = [
    LinkTypeDef(
        name="CAUSES",
        source_type="*",
        target_type="*",
        description="Causal relationship",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="LEADS_TO",
        source_type="*",
        target_type="*",
        description="Outcome chain",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="MITIGATED_BY",
        source_type="*",
        target_type="*",
        description="Risk mitigation",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="FOLLOWS",
        source_type="*",
        target_type="*",
        description="Workflow step ordering",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="TRIGGERS",
        source_type="*",
        target_type="*",
        description="Event triggers action",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="REQUIRES",
        source_type="*",
        target_type="*",
        description="Prerequisite relationship",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="MEASURED_BY",
        source_type="*",
        target_type="*",
        description="Entity measured by a metric",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="AFFECTS_METRIC",
        source_type="*",
        target_type="*",
        description="Process affects a metric",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="ESCALATES_TO",
        source_type="*",
        target_type="*",
        description="Escalation path",
        provenance=KnowledgeProvenance.SEEDED,
    ),
    LinkTypeDef(
        name="OWNED_BY_ROLE",
        source_type="*",
        target_type="*",
        description="Workflow owned by role",
        provenance=KnowledgeProvenance.SEEDED,
    ),
]

# ---------------------------------------------------------------------------
# Prompt serialization — delegates to agent/graph/introspect
# ---------------------------------------------------------------------------

def entity_schemas_for_prompt(
    *,
    filter_names: frozenset[str] | None = None,
) -> str:
    """Render entity type schemas as structured text for LLM prompts.

    Schemas are derived from the Pydantic models — no hand-maintained
    parallel declaration.

    Pass *filter_names* to restrict which types appear (e.g. pass
    ``resolver.PERSISTABLE_TYPES`` to show only ingestible entities).
    When *filter_names* is ``None``, all types are rendered.
    """
    return schemas_for_prompt(
        _ALL_TYPE_DEFS,
        link_defs=_STRUCTURAL_LINKS,
        filter_names=filter_names,
    )


# ---------------------------------------------------------------------------
# domain.yaml loader
# ---------------------------------------------------------------------------


def load_domain_yaml(path: Path | None = None) -> dict[str, Any]:
    """Load and parse the domain TBox YAML. Returns the full dict."""
    yaml_path = path or DOMAIN_YAML_PATH
    if not yaml_path.exists():
        return {}
    with open(yaml_path) as f:
        return yaml.safe_load(f) or {}

