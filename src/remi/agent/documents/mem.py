"""In-memory implementation of ContentStore."""

from __future__ import annotations

from typing import Any

from remi.agent.documents.types import ContentStore, DocumentContent, DocumentKind


class InMemoryContentStore(ContentStore):
    def __init__(self) -> None:
        self._docs: dict[str, DocumentContent] = {}

    async def save(self, document: DocumentContent) -> None:
        self._docs[document.id] = document

    async def get(self, document_id: str) -> DocumentContent | None:
        return self._docs.get(document_id)

    async def list_documents(self) -> list[DocumentContent]:
        return sorted(self._docs.values(), key=lambda d: d.uploaded_at, reverse=True)

    async def delete(self, document_id: str) -> bool:
        return self._docs.pop(document_id, None) is not None

    async def query_rows(
        self,
        document_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        doc = self._docs.get(document_id)
        if doc is None:
            return []

        rows = doc.rows
        if filters:
            for col, val in filters.items():
                if isinstance(val, list):
                    str_vals = {str(v) for v in val}
                    rows = [r for r in rows if str(r.get(col, "")) in str_vals]
                else:
                    rows = [r for r in rows if str(r.get(col, "")) == str(val)]

        return rows[:limit]

    async def search_documents(
        self,
        *,
        query: str | None = None,
        kind: DocumentKind | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[DocumentContent]:
        results = list(self._docs.values())

        if kind is not None:
            results = [d for d in results if d.kind == kind]

        if tags:
            tag_set = set(tags)
            results = [d for d in results if tag_set & set(d.tags)]

        if query:
            q = query.lower()
            results = [d for d in results if q in d.filename.lower()]

        results.sort(key=lambda d: d.uploaded_at, reverse=True)
        return results[:limit]

    async def update_tags(self, document_id: str, tags: list[str]) -> bool:
        doc = self._docs.get(document_id)
        if doc is None:
            return False
        doc.tags = tags
        return True
