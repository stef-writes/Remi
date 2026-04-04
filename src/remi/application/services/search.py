"""Portfolio-wide search — keyword + semantic hybrid over the vector index.

Exposes a fast, deterministic search (no LLM) suitable for typeahead UX.
Keyword matching fires first; semantic embedding only kicks in when
keyword results are sparse.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, Field

from remi.agent.vectors.types import Embedder, SearchResult, VectorStore

_log = structlog.get_logger(__name__)

_KEYWORD_FIELDS = ["manager_name", "property_name", "tenant_name", "company"]

_ENTITY_TYPE_LABELS: dict[str, str] = {
    "PropertyManager": "Manager",
    "Property": "Property",
    "Tenant": "Tenant",
    "Unit": "Unit",
    "MaintenanceRequest": "Maintenance",
    "DocumentRow": "Document",
}


class SearchHit(BaseModel, frozen=True):
    entity_id: str
    entity_type: str
    label: str
    title: str
    subtitle: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


def _title_for(result: SearchResult) -> str:
    meta = result.record.metadata
    et = result.record.source_entity_type
    if et == "PropertyManager":
        return meta.get("manager_name", result.record.source_entity_id)
    if et == "Property":
        return meta.get("property_name", result.record.source_entity_id)
    if et == "Tenant":
        return meta.get("tenant_name", result.record.source_entity_id)
    if et == "Unit":
        pname = meta.get("property_name", "")
        return f"Unit at {pname}" if pname else result.record.source_entity_id
    if et == "MaintenanceRequest":
        pname = meta.get("property_name", "")
        return f"Maintenance — {pname}" if pname else "Maintenance Request"
    if et == "DocumentRow":
        return meta.get("filename", "Document Row")
    return result.record.source_entity_id


def _subtitle_for(result: SearchResult) -> str:
    meta = result.record.metadata
    et = result.record.source_entity_type
    if et == "PropertyManager":
        parts: list[str] = []
        if meta.get("company"):
            parts.append(str(meta["company"]))
        if meta.get("property_count"):
            parts.append(f"{meta['property_count']} properties")
        return " · ".join(parts) if parts else ""
    if et == "Property":
        return meta.get("manager_name", "")
    if et == "Tenant":
        return meta.get("property_name", "")
    if et == "Unit":
        return meta.get("property_name", "")
    if et == "MaintenanceRequest":
        parts_m: list[str] = []
        if meta.get("priority"):
            parts_m.append(str(meta["priority"]))
        if meta.get("status"):
            parts_m.append(str(meta["status"]))
        return " · ".join(parts_m)
    if et == "DocumentRow":
        return meta.get("report_type", "")
    return ""


def _hit_from_result(result: SearchResult) -> SearchHit:
    et = result.record.source_entity_type
    return SearchHit(
        entity_id=result.record.source_entity_id,
        entity_type=et,
        label=_ENTITY_TYPE_LABELS.get(et, et),
        title=_title_for(result),
        subtitle=_subtitle_for(result),
        score=result.score,
        metadata=result.record.metadata,
    )


class SearchService:
    """Hybrid keyword + semantic search over the vector store."""

    def __init__(self, vector_store: VectorStore, embedder: Embedder) -> None:
        self._vs = vector_store
        self._embedder = embedder

    async def search(
        self,
        query: str,
        *,
        types: list[str] | None = None,
        manager_id: str | None = None,
        limit: int = 10,
    ) -> list[SearchHit]:
        if not query or not query.strip():
            return []

        query = query.strip()
        seen: dict[str, SearchHit] = {}

        keyword_results = await self._vs.metadata_text_search(
            query,
            fields=_KEYWORD_FIELDS,
            limit=limit * 2,
        )
        for r in keyword_results:
            hit = _hit_from_result(r)
            if types and hit.entity_type not in types:
                continue
            if manager_id and r.record.metadata.get("manager_id") != manager_id:
                continue
            if hit.entity_id not in seen:
                seen[hit.entity_id] = hit

        if len(seen) < limit:
            try:
                vector = await self._embedder.embed_one(query)
            except Exception:
                _log.warning("search_embed_failed", query=query[:100], exc_info=True)
                vector = None

            if vector is not None:
                metadata_filter: dict[str, Any] | None = None
                if manager_id:
                    metadata_filter = {"manager_id": manager_id}

                semantic_results = await self._vs.search(
                    vector,
                    limit=limit,
                    min_score=0.3,
                    metadata_filter=metadata_filter,
                )
                for r in semantic_results:
                    hit = _hit_from_result(r)
                    if types and hit.entity_type not in types:
                        continue
                    if hit.entity_id not in seen or hit.score > seen[hit.entity_id].score:
                        seen[hit.entity_id] = hit

        results = sorted(seen.values(), key=lambda h: h.score, reverse=True)
        return results[:limit]
