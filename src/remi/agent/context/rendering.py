"""LLM context rendering — projects typed perception into prose for injection.

``render_domain_context`` renders domain schema for agent priming (once).
``render_graph_context`` renders entity neighborhood for per-turn injection.
"""

from __future__ import annotations

from remi.agent.context.frame import ContextFrame
from remi.agent.signals import DomainSchema
from remi.types.text import estimate_tokens


def render_domain_context(domain: DomainSchema | None, **_kwargs: object) -> str:
    """Render the domain schema into a system message block for agent priming.

    Teaches the agent what entity types exist, how they relate, and what
    business processes the domain covers.  The agent uses this structural
    knowledge to orient its reasoning and data exploration.
    """
    if domain is None:
        return ""

    entity_types = getattr(domain, "entity_types", [])
    relationships = getattr(domain, "relationships", [])
    processes = getattr(domain, "processes", [])

    if not entity_types:
        return ""

    parts: list[str] = [
        f"## Domain Schema ({len(entity_types)} entity types, "
        f"{len(relationships)} relationships, {len(processes)} processes)\n"
    ]

    if entity_types:
        type_lines = []
        for et in entity_types:
            desc = et.description.split("\n")[0].strip() if et.description else ""
            fields = ", ".join(et.key_fields) if et.key_fields else ""
            line = f"- **{et.name}**: {desc}"
            if fields:
                line += f" — key fields: {fields}"
            type_lines.append(line)
        parts.append("**Entity types:**")
        parts.append("\n".join(type_lines))

    if relationships:
        rel_lines = [
            f"- {r.source} —[{r.name}]→ {r.target}: {r.description}" for r in relationships
        ]
        parts.append("\n**Relationships:**")
        parts.append("\n".join(rel_lines))

    if processes:
        proc_lines = []
        for p in processes:
            desc = p.description.split("\n")[0].strip() if p.description else ""
            involves = ", ".join(p.involves) if p.involves else ""
            line = f"- **{p.name}**: {desc}"
            if involves:
                line += f" (involves: {involves})"
            proc_lines.append(line)
        parts.append("\n**Business processes:**")
        parts.append("\n".join(proc_lines))

    return "\n".join(parts)


def render_graph_context(
    frame: ContextFrame,
    *,
    max_entities: int = 5,
    max_links_per_entity: int = 10,
    max_tokens: int = 4000,
) -> str:
    """Render resolved entities and their graph neighborhood for the LLM."""
    if not frame.entities:
        return ""

    entities = sorted(frame.entities, key=lambda e: e.score, reverse=True)[:max_entities]

    lines = [f"## Graph Context ({len(entities)} relevant entities)\n"]
    token_count = estimate_tokens("\n".join(lines))

    for entity in entities:
        entity_lines: list[str] = []
        name = entity.properties.get("name", entity.entity_id)
        entity_lines.append(
            f"### {entity.entity_type}: {name}"
            f"  (id=`{entity.entity_id}`, relevance={entity.score:.2f})"
        )

        display_props = {
            k: v for k, v in entity.properties.items() if k not in ("text",) and v is not None
        }
        if display_props:
            prop_parts = [f"{k}={v}" for k, v in list(display_props.items())[:8]]
            entity_lines.append(f"  Properties: {', '.join(prop_parts)}")

        links = frame.neighborhood.get(entity.entity_id, [])[:max_links_per_entity]
        if links:
            entity_lines.append("  Relationships:")
            for link in links:
                direction = "\u2192" if link.source_id == entity.entity_id else "\u2190"
                other_id = link.target_id if link.source_id == entity.entity_id else link.source_id
                scalars = {
                    k: v for k, v in link.properties.items()
                    if k not in ("target_type",) and isinstance(v, (str, int, float, bool))
                }
                scalar_str = (
                    " (" + ", ".join(f"{k}={v}" for k, v in list(scalars.items())[:4]) + ")"
                    if scalars else ""
                )
                entity_lines.append(
                    f"  - {direction} {link.link_type} \u2192 `{other_id}`{scalar_str}"
                )

        entity_lines.append("")

        chunk_cost = estimate_tokens("\n".join(entity_lines))
        if token_count + chunk_cost > max_tokens:
            break
        lines.extend(entity_lines)
        token_count += chunk_cost

    if len(lines) <= 1:
        return ""

    lines.append(
        "This graph context was pre-fetched based on your question. Use it to ground your answer."
    )
    return "\n".join(lines)
