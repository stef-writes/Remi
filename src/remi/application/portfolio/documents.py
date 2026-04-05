"""Documents — list, filter, and tag queries."""

from __future__ import annotations

from remi.application.core.models import Document
from remi.application.core.protocols import PropertyStore


class DocumentResolver:
    """Read-side resolver for document queries."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_documents(
        self,
        *,
        unit_id: str | None = None,
        property_id: str | None = None,
        manager_id: str | None = None,
        kind: str | None = None,
        tags: str | None = None,
        q: str | None = None,
        sort: str = "newest",
        limit: int = 50,
    ) -> list[Document]:
        docs = await self._ps.list_documents(
            unit_id=unit_id,
            property_id=property_id,
            manager_id=manager_id,
        )

        if kind:
            docs = [d for d in docs if d.kind == kind]
        if tags:
            tag_set = {t.strip() for t in tags.split(",") if t.strip()}
            docs = [d for d in docs if tag_set & set(d.tags)]
        if q:
            ql = q.lower()
            docs = [d for d in docs if ql in d.filename.lower()]

        if sort == "oldest":
            docs.sort(key=lambda d: d.uploaded_at)
        elif sort == "name":
            docs.sort(key=lambda d: d.filename.lower())
        else:
            docs.sort(key=lambda d: d.uploaded_at, reverse=True)

        return docs[:limit]

    async def list_tags(self) -> list[str]:
        docs = await self._ps.list_documents()
        all_tags: set[str] = set()
        for d in docs:
            all_tags.update(d.tags)
        return sorted(all_tags)
