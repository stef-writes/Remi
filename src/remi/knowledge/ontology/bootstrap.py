"""Bootstrap the ontology — register core types, link types, and seed
operational PM knowledge from domain.yaml (TBox + ABox seeds).

Called once during container initialization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from remi.models.ontology import (
    KnowledgeProvenance,
    LinkTypeDef,
    ObjectTypeDef,
    OntologyStore,
    PropertyDef,
)
from remi.shared.paths import DOMAIN_YAML_PATH

# ---------------------------------------------------------------------------
# Core object type definitions (matching domain models)
# These remain in code because they mirror Pydantic model shapes.
# ---------------------------------------------------------------------------

_CORE_TYPES: list[ObjectTypeDef] = [
    ObjectTypeDef(
        name="PropertyManager",
        plural_name="PropertyManagers",
        description="A property manager overseeing one or more portfolios",
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="name", data_type="string", required=True),
            PropertyDef(name="email", data_type="string", required=True),
            PropertyDef(name="company", data_type="string"),
            PropertyDef(name="phone", data_type="string"),
        ),
    ),
    ObjectTypeDef(
        name="Portfolio",
        plural_name="Portfolios",
        description="A collection of properties managed together",
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="manager_id", data_type="string", required=True),
            PropertyDef(name="name", data_type="string", required=True),
            PropertyDef(name="description", data_type="string"),
        ),
    ),
    ObjectTypeDef(
        name="Property",
        plural_name="Properties",
        description="A real estate property (building or complex)",
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="portfolio_id", data_type="string", required=True),
            PropertyDef(name="name", data_type="string", required=True),
            PropertyDef(name="address", data_type="object"),
            PropertyDef(
                name="property_type",
                data_type="enum",
                enum_values=["residential", "commercial", "mixed", "industrial"],
            ),
            PropertyDef(name="year_built", data_type="number"),
            PropertyDef(name="total_units", data_type="number"),
        ),
    ),
    ObjectTypeDef(
        name="Unit",
        plural_name="Units",
        description="A rentable unit within a property",
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="property_id", data_type="string", required=True),
            PropertyDef(name="unit_number", data_type="string", required=True),
            PropertyDef(name="bedrooms", data_type="number"),
            PropertyDef(name="bathrooms", data_type="number"),
            PropertyDef(name="sqft", data_type="number"),
            PropertyDef(name="market_rent", data_type="decimal"),
            PropertyDef(name="current_rent", data_type="decimal"),
            PropertyDef(
                name="status",
                data_type="enum",
                enum_values=["vacant", "occupied", "maintenance", "offline"],
            ),
        ),
    ),
    ObjectTypeDef(
        name="Lease",
        plural_name="Leases",
        description="A lease agreement for a unit",
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="unit_id", data_type="string", required=True),
            PropertyDef(name="tenant_id", data_type="string", required=True),
            PropertyDef(name="property_id", data_type="string", required=True),
            PropertyDef(name="start_date", data_type="date", required=True),
            PropertyDef(name="end_date", data_type="date", required=True),
            PropertyDef(name="monthly_rent", data_type="decimal", required=True),
            PropertyDef(name="deposit", data_type="decimal"),
            PropertyDef(
                name="status",
                data_type="enum",
                enum_values=["active", "expired", "terminated", "pending"],
            ),
        ),
    ),
    ObjectTypeDef(
        name="Tenant",
        plural_name="Tenants",
        description="A person or entity leasing a unit",
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="name", data_type="string", required=True),
            PropertyDef(name="email", data_type="string", required=True),
            PropertyDef(name="phone", data_type="string"),
        ),
    ),
    ObjectTypeDef(
        name="MaintenanceRequest",
        plural_name="MaintenanceRequests",
        description="A maintenance work order for a unit",
        properties=(
            PropertyDef(name="id", data_type="string", required=True),
            PropertyDef(name="unit_id", data_type="string", required=True),
            PropertyDef(name="property_id", data_type="string", required=True),
            PropertyDef(name="tenant_id", data_type="string"),
            PropertyDef(
                name="category",
                data_type="enum",
                enum_values=[
                    "plumbing",
                    "electrical",
                    "hvac",
                    "appliance",
                    "structural",
                    "general",
                    "other",
                ],
            ),
            PropertyDef(
                name="priority",
                data_type="enum",
                enum_values=["low", "medium", "high", "emergency"],
            ),
            PropertyDef(name="title", data_type="string"),
            PropertyDef(name="description", data_type="string"),
            PropertyDef(
                name="status",
                data_type="enum",
                enum_values=["open", "in_progress", "completed", "cancelled"],
            ),
            PropertyDef(name="cost", data_type="decimal"),
            PropertyDef(name="vendor", data_type="string"),
        ),
    ),
]

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
# domain.yaml loader
# ---------------------------------------------------------------------------


def load_domain_yaml(path: Path | None = None) -> dict[str, Any]:
    """Load and parse the domain ontology YAML. Returns the full dict."""
    yaml_path = path or DOMAIN_YAML_PATH
    if not yaml_path.exists():
        return {}
    with open(yaml_path) as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Bootstrap entry point
# ---------------------------------------------------------------------------


async def bootstrap_ontology(
    store: OntologyStore,
    domain_yaml_path: Path | None = None,
) -> None:
    """Register core types, link types, and seed operational knowledge."""

    domain = load_domain_yaml(domain_yaml_path)

    for type_def in _CORE_TYPES:
        await store.define_object_type(type_def)

    for link_def in _STRUCTURAL_LINKS:
        await store.define_link_type(link_def)
    for link_def in _OPERATIONAL_LINKS:
        await store.define_link_type(link_def)

    # Seed ABox workflows from domain.yaml
    abox = domain.get("abox", {})
    for wf in abox.get("workflows", []):
        steps = [(s["id"], s["description"]) for s in wf.get("steps", [])]
        await _seed_workflow(store, wf["name"], steps)

    # Seed causal chains from domain.yaml TBox
    tbox = domain.get("tbox", {})
    for chain in tbox.get("causal_chains", []):
        source_id = f"cause:{chain['cause']}"
        target_id = f"cause:{chain['effect']}"
        description = chain["description"]
        await store.codify(
            "cause", {"description": description}, provenance=KnowledgeProvenance.SEEDED
        )
        await store.put_link(
            source_id, "CAUSES", target_id, properties={"description": description}
        )

    # Seed policies from domain.yaml TBox
    for policy in tbox.get("policies", []):
        await store.codify(
            "policy",
            {
                "description": policy["description"],
                "trigger": policy["trigger"],
                "deontic": policy.get("deontic", "SHOULD"),
            },
            provenance=KnowledgeProvenance.SEEDED,
        )


async def _seed_workflow(
    store: OntologyStore,
    workflow_name: str,
    steps: list[tuple[str, str]],
) -> None:
    for step_id, description in steps:
        await store.put_object(
            "process",
            step_id,
            {
                "name": step_id.split(":")[-1],
                "description": description,
                "workflow": workflow_name,
                "provenance": KnowledgeProvenance.SEEDED.value,
            },
        )

    for i in range(len(steps) - 1):
        await store.put_link(steps[i][0], "FOLLOWS", steps[i + 1][0])
