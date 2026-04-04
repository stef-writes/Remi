"""Vector retrieval tools — semantic search for LLM agents.

Provides: semantic_search, vector_stats.
"""

from __future__ import annotations

from typing import Any

from remi.agent.types import ToolArg, ToolDefinition, ToolRegistry
from remi.agent.vectors.types import Embedder, VectorStore


def register_vector_tools(
    registry: ToolRegistry,
    *,
    vector_store: VectorStore,
    embedder: Embedder,
    search_hint: str = "",
    entity_type_hint: str = "",
    scope_filter_args: list[ToolArg] | None = None,
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
        for farg in (scope_filter_args or []):
            if val := args.get(farg.name):
                metadata_filter = metadata_filter or {}
                metadata_filter[farg.name] = val

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

    base_desc = (
        "Search for entities or data rows by meaning, not exact text. "
        "Finds records whose text is semantically similar to your query."
    )
    if search_hint:
        base_desc = f"{base_desc} {search_hint}"

    entity_type_desc = entity_type_hint or "Filter by entity type"

    search_args = [
        ToolArg(
            name="query",
            description="Natural language description of what you're looking for",
            required=True,
        ),
        ToolArg(name="entity_type", description=entity_type_desc),
        *(scope_filter_args or []),
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
    ]

    registry.register(
        "semantic_search",
        semantic_search,
        ToolDefinition(
            name="semantic_search",
            description=base_desc,
            args=search_args,
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
