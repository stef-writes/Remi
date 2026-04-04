"""REMI knowledge graph schema — type registry, link types, and prompt helpers.

Entity type definitions are **derived** from the Pydantic models in
``application.core.models`` via ``agent.graph.retrieval.introspect``.  This
module owns the RE-specific registry (which models to introspect, descriptions,
plural names), the structural and operational link types, the FK projection
map, and the ``entity_schemas_for_prompt`` entry point.

KG-only types that have no Pydantic model (e.g. ``Annotation``) are declared
as supplemental ``ObjectTypeDef`` instances here.  ``Note`` and ``ActionItem``
are first-class domain models and live in the core registry above.

Seeding the knowledge graph is in ``application.infra.ontology.seed``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from remi.agent.graph.retrieval.introspect import (
    pydantic_to_type_defs,
    schemas_for_prompt,
)
from remi.agent.graph.types import (
    FKProjection,
    KnowledgeProvenance,
    LinkTypeDef,
    ObjectTypeDef,
    ProjectionMapping,
    PropertyDef,
)
from remi.application.core.models import (
    ActionItem,
    Lease,
    MaintenanceRequest,
    Note,
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

_MODEL_REGISTRY: list[tuple[type, str] | tuple[type, str, str]] = [
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
        "A director-created action item for tracking follow-ups on managers, "
        "properties, or tenants",
        "ActionItems",
    ),
    (
        Note,
        "A note attached to any domain entity — user-entered, report-derived, or AI-inferred",
        "Notes",
    ),
]

# Derived at import time — stays in sync with models.py automatically.
_CORE_TYPE_DEFS: list[ObjectTypeDef] = pydantic_to_type_defs(_MODEL_REGISTRY)

# ---------------------------------------------------------------------------
# KG-only supplemental types (no Pydantic model)
# ---------------------------------------------------------------------------

_SUPPLEMENTAL_TYPES: list[ObjectTypeDef] = [
    ObjectTypeDef(
        name="Annotation",
        plural_name="Annotations",
        description=(
            "Unstructured text attached to any entity — notes, comments,"
            " conflict records, user context. Searchable and embeddable."
        ),
        properties=(
            PropertyDef(name="annotation_id", data_type="string", required=True),
            PropertyDef(name="content", data_type="string", required=True),
            PropertyDef(
                name="annotation_type",
                data_type="enum",
                enum_values=["note", "comment", "conflict", "user_context"],
            ),
            PropertyDef(name="target_entity_id", data_type="string"),
            PropertyDef(name="target_entity_type", data_type="string"),
            PropertyDef(name="source", data_type="string"),
            PropertyDef(name="confidence", data_type="decimal"),
            PropertyDef(name="extracted_at", data_type="datetime"),
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
    LinkTypeDef(
        name="TRACKS",
        source_type="ActionItem",
        target_type="*",
        description="Action item tracks a manager, property, or tenant",
    ),
    LinkTypeDef(
        name="HAS_ANNOTATION",
        source_type="*",
        target_type="Annotation",
        description="Entity has an attached annotation (note, comment, conflict, user context)",
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
# FK-to-edge projection mapping — RE-specific schema for the generic projector
# ---------------------------------------------------------------------------

FK_PROJECTION_MAP: ProjectionMapping = {
    "Unit": [FKProjection("property_id", "BELONGS_TO", "Property")],
    "Lease": [
        FKProjection("unit_id", "COVERS", "Unit"),
        FKProjection("tenant_id", "SIGNED_BY", "Tenant"),
    ],
    "Property": [
        FKProjection("portfolio_id", "IN_PORTFOLIO", "Portfolio"),
        FKProjection("manager_id", "MANAGED_BY", "PropertyManager"),
        FKProjection("owner_id", "OWNED_BY", "Owner"),
    ],
    "MaintenanceRequest": [
        FKProjection("unit_id", "AFFECTS", "Unit"),
        FKProjection("vendor_id", "SERVICED_BY", "Vendor"),
    ],
    # Note uses entity_id as a polymorphic FK — the edge direction is
    # entity → HAS_NOTE → note, so we project from the *subject* side.
    # The projector writes source=entity_id, link=HAS_NOTE, target=note_id.
    "Note": [FKProjection("entity_id", "HAS_NOTE", "*")],
    # ActionItem tracks follow-ups on managers, properties, and tenants.
    # All three are optional FKs; the projector skips null values automatically.
    "ActionItem": [
        FKProjection("manager_id", "TRACKS", "PropertyManager"),
        FKProjection("property_id", "TRACKS", "Property"),
        FKProjection("tenant_id", "TRACKS", "Tenant"),
    ],
}

ALL_STRUCTURAL_LINKS = _STRUCTURAL_LINKS
ALL_OPERATIONAL_LINKS = _OPERATIONAL_LINKS

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
    ``application.services.ingestion.resolver.PERSISTABLE_TYPES`` to show
    only ingestible entities). When *filter_names* is ``None``, all types
    are rendered.
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
