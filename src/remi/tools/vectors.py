"""Vector retrieval tools — semantic search for LLM agents.

Provides: semantic_search, vector_stats.
"""

from __future__ import annotations

from typing import Any

from remi.models.retrieval import Embedder, VectorStore
from remi.models.tools import ToolArg, ToolDefinition, ToolRegistry


def register_vector_tools(
    registry: ToolRegistry,
    *,
    vector_store: VectorStore,
    embedder: Embedder,
) -> None:
    vs = vector_store
    emb = embedder

    # -- semantic_search -------------------------------------------------------

    async def semantic_search(args: dict[str, Any]) -> Any:
        query = args.get("query", "")
        if not query:
            return {"error": "query is required"}

        query_vector = await emb.embed_one(query)

        entity_type = args.get("entity_type")
        limit = int(args.get("limit", 10))
        min_score = float(args.get("min_score", 0.3))

        metadata_filter: dict[str, Any] | None = None
        if manager_id := args.get("manager_id"):
            metadata_filter = {"manager_id": manager_id}
        if property_id := args.get("property_id"):
            metadata_filter = metadata_filter or {}
            metadata_filter["property_id"] = property_id

        results = await vs.search(
            query_vector,
            limit=limit,
            entity_type=entity_type,
            metadata_filter=metadata_filter,
            min_score=min_score,
        )

        return [
            {
                "entity_id": r.entity_id,
                "entity_type": r.entity_type,
                "score": r.score,
                "text": r.text,
                "source_field": r.record.source_field,
                "metadata": r.record.metadata,
            }
            for r in results
        ]

    registry.register(
        "semantic_search",
        semantic_search,
        ToolDefinition(
            name="semantic_search",
            description=(
                "Search for entities or raw report rows by meaning, not exact text. "
                "Finds tenants, units, properties, maintenance requests, and individual "
                "rows from uploaded documents whose text is semantically similar to your "
                "query. Use this for fuzzy lookups ('problem tenants', 'mold issues', "
                "'that building on Ella Street', 'overdue rent on unit 4B') where exact "
                "filters won't work. DocumentRow results include the original report row "
                "as text plus metadata with document_id, filename, report_type, and row_index."
            ),
            args=[
                ToolArg(
                    name="query",
                    description="Natural language description of what you're looking for",
                    required=True,
                ),
                ToolArg(
                    name="entity_type",
                    description=(
                        "Filter by type: Tenant, Unit, Property, MaintenanceRequest, DocumentRow"
                    ),
                ),
                ToolArg(
                    name="manager_id",
                    description="Filter results to a specific manager's entities",
                ),
                ToolArg(
                    name="property_id",
                    description="Filter results to a specific property's entities",
                ),
                ToolArg(
                    name="limit",
                    description="Max results to return (default: 10)",
                    type="integer",
                ),
                ToolArg(
                    name="min_score",
                    description="Minimum similarity score 0-1 (default: 0.3)",
                    type="number",
                ),
            ],
        ),
    )

    # -- vector_stats ----------------------------------------------------------

    async def vector_stats(args: dict[str, Any]) -> Any:
        total = await vs.count()
        by_type = await vs.stats()
        return {
            "total_embeddings": total,
            "by_entity_type": by_type,
            "embedder_dimension": emb.dimension,
        }

    registry.register(
        "vector_stats",
        vector_stats,
        ToolDefinition(
            name="vector_stats",
            description=(
                "Get statistics about the vector embedding index: "
                "total count, counts by entity type."
            ),
            args=[],
        ),
    )
