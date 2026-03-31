"""Postgres-backed DocumentStore using SQLModel + asyncpg."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from remi.db.tables import DocumentRow
from remi.models.documents import Document, DocumentStore


def _json_safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert datetime/date values in row dicts to ISO strings for JSON storage."""
    out: list[dict[str, Any]] = []
    for row in rows:
        safe: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                safe[k] = v.isoformat()
            elif isinstance(v, date):
                safe[k] = v.isoformat()
            else:
                safe[k] = v
        out.append(safe)
    return out


def _doc_from_row(row: DocumentRow) -> Document:
    return Document(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        uploaded_at=row.uploaded_at,
        row_count=row.row_count,
        column_names=row.column_names,
        rows=row.rows,
        metadata=row.doc_metadata,
    )


def _doc_to_row(doc: Document) -> DocumentRow:
    return DocumentRow(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        uploaded_at=doc.uploaded_at,
        row_count=doc.row_count,
        column_names=list(doc.column_names),
        rows=_json_safe_rows(doc.rows),
        doc_metadata=dict(doc.metadata),
    )


class PostgresDocumentStore(DocumentStore):
    """DocumentStore backed by Postgres via SQLModel async sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, document: Document) -> None:
        async with self._session_factory() as session:
            existing = await session.get(DocumentRow, document.id)
            if existing:
                existing.filename = document.filename
                existing.content_type = document.content_type
                existing.uploaded_at = document.uploaded_at
                existing.row_count = document.row_count
                existing.column_names = list(document.column_names)
                existing.rows = _json_safe_rows(document.rows)
                existing.doc_metadata = dict(document.metadata)
                session.add(existing)
            else:
                session.add(_doc_to_row(document))
            await session.commit()

    async def get(self, document_id: str) -> Document | None:
        async with self._session_factory() as session:
            row = await session.get(DocumentRow, document_id)
            return _doc_from_row(row) if row else None

    async def list_documents(self) -> list[Document]:
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
