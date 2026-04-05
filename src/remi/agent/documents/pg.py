"""Postgres-backed ContentStore using SQLModel + asyncpg."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from remi.agent.db.tables import DocumentRow
from remi.agent.documents.types import (
    ContentStore,
    DocumentContent,
    DocumentKind,
    TextChunk,
)


def _json_safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert datetime/date values in row dicts to ISO strings for JSON storage."""
    out: list[dict[str, Any]] = []
    for row in rows:
        safe: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, (datetime, date)):
                safe[k] = v.isoformat()
            else:
                safe[k] = v
        out.append(safe)
    return out


def _chunks_to_json(chunks: list[TextChunk]) -> list[dict[str, Any]]:
    return [c.model_dump() for c in chunks]


def _chunks_from_json(data: list[dict[str, Any]]) -> list[TextChunk]:
    return [TextChunk(**c) for c in data]


def _doc_from_row(row: DocumentRow) -> DocumentContent:
    meta = row.doc_metadata or {}
    return DocumentContent(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        uploaded_at=row.uploaded_at,
        kind=DocumentKind(meta.get("kind", "tabular")),
        row_count=row.row_count,
        column_names=row.column_names,
        rows=row.rows,
        chunks=_chunks_from_json(meta.get("chunks", [])),
        raw_text=meta.get("raw_text", ""),
        page_count=meta.get("page_count", 0),
        tags=meta.get("tags", []),
        size_bytes=meta.get("size_bytes", 0),
        metadata={k: v for k, v in meta.items() if k not in {
            "kind", "chunks", "raw_text", "page_count", "tags", "size_bytes",
        }},
    )


def _doc_to_row(doc: DocumentContent) -> DocumentRow:
    meta = dict(doc.metadata)
    meta.update({
        "kind": doc.kind.value,
        "chunks": _chunks_to_json(doc.chunks),
        "raw_text": doc.raw_text,
        "page_count": doc.page_count,
        "tags": doc.tags,
        "size_bytes": doc.size_bytes,
    })
    return DocumentRow(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        uploaded_at=doc.uploaded_at,
        row_count=doc.row_count,
        column_names=list(doc.column_names),
        rows=_json_safe_rows(doc.rows),
        doc_metadata=meta,
    )


class PostgresContentStore(ContentStore):
    """ContentStore backed by Postgres via SQLModel async sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, document: DocumentContent) -> None:
        row = _doc_to_row(document)
        async with self._session_factory() as session:
            existing = await session.get(DocumentRow, document.id)
            if existing:
                existing.filename = row.filename
                existing.content_type = row.content_type
                existing.uploaded_at = row.uploaded_at
                existing.row_count = row.row_count
                existing.column_names = row.column_names
                existing.rows = row.rows
                existing.doc_metadata = row.doc_metadata
                session.add(existing)
            else:
                session.add(row)
            await session.commit()

    async def get(self, document_id: str) -> DocumentContent | None:
        async with self._session_factory() as session:
            row = await session.get(DocumentRow, document_id)
            return _doc_from_row(row) if row else None

    async def list_documents(self) -> list[DocumentContent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(DocumentRow).order_by(DocumentRow.uploaded_at.desc())  # type: ignore[arg-type]
            )
            return [_doc_from_row(r) for r in result.scalars().all()]

    async def delete(self, document_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(DocumentRow, document_id)
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def query_rows(
        self,
        document_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        doc = await self.get(document_id)
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
        docs = await self.list_documents()

        if kind is not None:
            docs = [d for d in docs if d.kind == kind]

        if tags:
            tag_set = set(tags)
            docs = [d for d in docs if tag_set & set(d.tags)]

        if query:
            q = query.lower()
            docs = [d for d in docs if q in d.filename.lower()]

        return docs[:limit]

    async def update_tags(self, document_id: str, tags: list[str]) -> bool:
        async with self._session_factory() as session:
            row = await session.get(DocumentRow, document_id)
            if row is None:
                return False
            meta = dict(row.doc_metadata or {})
            meta["tags"] = tags
            row.doc_metadata = meta
            session.add(row)
            await session.commit()
            return True
