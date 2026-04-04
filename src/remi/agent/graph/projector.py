"""Generic FK-to-edge graph projector — domain-agnostic.

Given a mapping of ``(entity_type, fk_field) → (link_type, target_type)``
and entity data, materialises relationship edges in the knowledge graph.
The projector knows nothing about any specific domain — the caller provides
the mapping (e.g. ``Unit.property_id → BELONGS_TO → Property``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.graph.types import (
    FactProvenance,
    KnowledgeProvenance,
    ProjectionMapping,
)

_log = structlog.get_logger(__name__)

_PROJECTION_PROVENANCE = FactProvenance(
    source="projection",
    confidence=1.0,
    provenance_type=KnowledgeProvenance.DATA_DERIVED,
)


@dataclass
class ProjectionResult:
    """Summary of a projection run."""

    edges_created: int = 0
    edges_skipped: int = 0
    errors: int = 0
    details: list[str] = field(default_factory=list)


class GraphProjector:
    """Materialises FK relationships as graph edges.

    Constructed once with a ``KnowledgeGraph`` and a ``ProjectionMapping``.
    Call ``project_entity`` after each entity upsert, or ``project_all``
    for a bulk rebuild.
    """

    def __init__(
        self,
        knowledge_graph: KnowledgeGraph,
        mappings: ProjectionMapping,
    ) -> None:
        self._kg = knowledge_graph
        self._mappings = mappings

    async def project_entity(
        self,
        entity_type: str,
        entity_id: str,
        entity_data: dict[str, object],
    ) -> int:
        """Project edges for a single entity.  Returns number of edges written."""
        projections = self._mappings.get(entity_type)
        if not projections:
            return 0

        count = 0
        for proj in projections:
            target_id = entity_data.get(proj.fk_field)
            if not target_id or not str(target_id).strip():
                continue
            target_id_str = str(target_id).strip()
            try:
                await self._kg.put_link(
                    entity_id,
                    proj.link_type,
                    target_id_str,
                    properties={
                        "provenance_source": "projection",
                        "projected_at": datetime.now(UTC).isoformat(),
                    },
                )
                count += 1
            except Exception:
                _log.warning(
                    "projection_edge_failed",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    link_type=proj.link_type,
                    target_id=target_id_str,
                    exc_info=True,
                )
        return count

    async def project_all(
        self,
        entities_by_type: dict[str, list[dict[str, object]]],
    ) -> ProjectionResult:
        """Bulk-project edges for all provided entities."""
        result = ProjectionResult()

        for entity_type, entities in entities_by_type.items():
            projections = self._mappings.get(entity_type)
            if not projections:
                continue

            for entity_data in entities:
                entity_id = str(entity_data.get("id", "")).strip()
                if not entity_id:
                    result.edges_skipped += 1
                    continue
                try:
                    count = await self.project_entity(entity_type, entity_id, entity_data)
                    result.edges_created += count
                except Exception:
                    _log.warning(
                        "bulk_projection_failed",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        exc_info=True,
                    )
                    result.errors += 1

        _log.info(
            "projection_complete",
            edges_created=result.edges_created,
            edges_skipped=result.edges_skipped,
            errors=result.errors,
        )
        return result
