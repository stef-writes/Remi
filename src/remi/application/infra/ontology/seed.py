"""Knowledge graph seeding — register types, link types, and operational knowledge.

Separated from ``schema`` so the declaration module stays pure data
and the seeding module owns the I/O-bound async work.

Operational knowledge (causal chains, policies, workflows) is loaded via
``DomainTBox.from_yaml`` so the YAML shape is validated against typed Pydantic
models before any graph write — a malformed domain.yaml raises at seed time,
not silently at query time.
"""

from __future__ import annotations

from pathlib import Path

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.graph.types import KnowledgeProvenance
from remi.agent.signals.tbox import CausalChain, DomainTBox, Policy, WorkflowSeed
from remi.application.infra.ontology.schema import (
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

    raw = load_domain_yaml(domain_yaml_path)
    tbox = DomainTBox.from_yaml(raw)

    for type_def in _ALL_TYPE_DEFS:
        await store.define_object_type(type_def)

    for link_def in _STRUCTURAL_LINKS:
        await store.define_link_type(link_def)
    for link_def in _OPERATIONAL_LINKS:
        await store.define_link_type(link_def)

    for wf in tbox.workflows:
        await _seed_workflow(store, wf)

    for chain in tbox.causal_chains:
        await _seed_causal_chain(store, chain)

    for policy in tbox.policies:
        await _seed_policy(store, policy)


async def _seed_workflow(store: KnowledgeGraph, wf: WorkflowSeed) -> None:
    for step in wf.steps:
        await store.put_object(
            "process",
            step.id,
            {
                "name": step.id.split(":")[-1],
                "description": step.description,
                "workflow": wf.name,
                "provenance": KnowledgeProvenance.SEEDED.value,
            },
        )

    for i in range(len(wf.steps) - 1):
        await store.put_link(wf.steps[i].id, "FOLLOWS", wf.steps[i + 1].id)


async def _seed_causal_chain(store: KnowledgeGraph, chain: CausalChain) -> None:
    source_id = f"cause:{chain.cause}"
    target_id = f"cause:{chain.effect}"
    await store.codify(
        "cause",
        {"description": chain.description},
        provenance=KnowledgeProvenance.SEEDED,
    )
    await store.put_link(
        source_id, "CAUSES", target_id, properties={"description": chain.description}
    )


async def _seed_policy(store: KnowledgeGraph, policy: Policy) -> None:
    await store.codify(
        "policy",
        {
            "description": policy.description,
            "trigger": policy.trigger,
            "deontic": policy.deontic.value,
        },
        provenance=KnowledgeProvenance.SEEDED,
    )
