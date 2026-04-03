"""Knowledge graph seeding — register types, link types, and operational knowledge.

Separated from ``schema`` so the declaration module stays pure data
and the seeding module owns the I/O-bound async work.
"""

from __future__ import annotations

from pathlib import Path

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.graph.types import KnowledgeProvenance
from remi.domain.ontology.schema import (
    _ALL_TYPE_DEFS,
    _OPERATIONAL_LINKS,
    _STRUCTURAL_LINKS,
    load_domain_yaml,
)


async def seed_knowledge_graph(
    store: KnowledgeGraph,
    domain_yaml_path: Path | None = None,
) -> None:
    """Register core types, link types, and seed operational knowledge."""

    domain = load_domain_yaml(domain_yaml_path)

    for type_def in _ALL_TYPE_DEFS:
        await store.define_object_type(type_def)

    for link_def in _STRUCTURAL_LINKS:
        await store.define_link_type(link_def)
    for link_def in _OPERATIONAL_LINKS:
        await store.define_link_type(link_def)

    abox = domain.get("abox", {})
    for wf in abox.get("workflows", []):
        steps = [(s["id"], s["description"]) for s in wf.get("steps", [])]
        await _seed_workflow(store, wf["name"], steps)

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
    store: KnowledgeGraph,
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
