"""Portfolio search tool — hybrid keyword + semantic search for LLM agents.

Provides: portfolio_search.
"""

from __future__ import annotations

from typing import Any

from remi.agent.types import ToolArg, ToolDefinition, ToolRegistry
from remi.application.services.search import SearchService


def register_search_tools(
    registry: ToolRegistry,
    *,
    search_service: SearchService,
) -> None:

    async def portfolio_search(args: dict[str, Any]) -> Any:
        query = args.get("query", "")
        if not query:
            return {"error": "query is required"}

        types_raw = args.get("types")
        types: list[str] | None = None
        if isinstance(types_raw, str):
            types = [t.strip() for t in types_raw.split(",") if t.strip()]
        elif isinstance(types_raw, list):
            types = types_raw

        manager_id = args.get("manager_id")
        limit = int(args.get("limit", 10))

        results = await search_service.search(
            query, types=types, manager_id=manager_id, limit=limit,
        )

        return [
            {
                "entity_id": h.entity_id,
                "entity_type": h.entity_type,
                "title": h.title,
                "subtitle": h.subtitle,
                "score": h.score,
                "metadata": h.metadata,
            }
            for h in results
        ]

    registry.register(
        "portfolio_search",
        portfolio_search,
        ToolDefinition(
            name="portfolio_search",
            description=(
                "Fast portfolio-wide search across managers, properties, tenants, "
                "units, and maintenance requests. Combines keyword matching on names "
                "with semantic similarity for fuzzy queries. Use this to look up "
                "entities by name, find properties by address or description, or "
                "locate tenants. Returns structured results with titles and metadata — "
                "much faster than scanning all entities manually. For exact data "
                "retrieval after finding an entity, use the appropriate workflow or "
                "sandbox tool with the returned entity_id."
            ),
            args=[
                ToolArg(
                    name="query",
                    description="Search query — a name, address, "
                    "description, or natural language phrase",
                    required=True,
                ),
                ToolArg(
                    name="types",
                    description=(
                        "Comma-separated entity types to filter: "
                        "PropertyManager, Property, Tenant, Unit, MaintenanceRequest, DocumentRow"
                    ),
                ),
                ToolArg(
                    name="manager_id",
                    description="Scope results to a specific manager's entities",
                ),
                ToolArg(
                    name="limit",
                    description="Max results to return (default: 10)",
                    type="integer",
                ),
            ],
        ),
    )
