"""In-memory implementation of DocumentStore."""

from __future__ import annotations

from typing import Any

from remi.models.documents import Document, DocumentStore


class InMemoryDocumentStore(DocumentStore):
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}

    async def save(self, document: Document) -> None:
        self._docs[document.id] = document

    async def get(self, document_id: str) -> Document | None:
        return self._docs.get(document_id)

    async def list_documents(self) -> list[Document]:
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
