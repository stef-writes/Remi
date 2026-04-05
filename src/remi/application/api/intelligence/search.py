"""Search router — fast portfolio-wide typeahead search."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from remi.application.services.search import SearchHit
from remi.shell.api.dependencies import Ctr

router = APIRouter(prefix="/search", tags=["search"])


class SearchResponse(BaseModel, frozen=True):
    query: str
    results: list[SearchHit]
    total: int


@router.get("", response_model=SearchResponse)
async def search(
    c: Ctr,
    q: str = Query(description="Search query"),
    types: str | None = Query(
        default=None,
        description="Comma-separated entity types to filter (e.g. PropertyManager,Property)",
    ),
    manager_id: str | None = Query(default=None, description="Scope to a manager"),
    limit: int = Query(default=10, ge=1, le=50),
) -> SearchResponse:
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None
    results = await c.search_service.search(q, types=type_list, manager_id=manager_id, limit=limit)
    return SearchResponse(query=q, results=results, total=len(results))
