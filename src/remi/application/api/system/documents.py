"""Document upload and query REST endpoints — knowledge base API."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Body, File, Form, Query, UploadFile

from remi.application.api.system.document_schemas import (
    ChunkItem,
    CorrectRowRequest,
    CorrectRowResponse,
    DeleteResponse,
    DocumentChunksResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentRowsResponse,
    KnowledgeInfo,
    ReviewItemSchema,
    ReviewOptionSchema,
    TagsResponse,
    TagUpdateRequest,
    UploadResponse,
)
from remi.application.core.models import Document
from remi.application.realtime.connection_manager import manager as ws_manager
from remi.shell.api.dependencies import Ctr
from remi.types.errors import DomainError, NotFoundError

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _review_items_to_schemas(
    items: list[object],
) -> list[ReviewItemSchema]:
    """Convert internal ReviewItem dataclasses to API schemas."""
    return [
        ReviewItemSchema(
            kind=ri.kind,  # type: ignore[attr-defined]
            severity=ri.severity,  # type: ignore[attr-defined]
            message=ri.message,  # type: ignore[attr-defined]
            row_index=ri.row_index,  # type: ignore[attr-defined]
            entity_type=ri.entity_type,  # type: ignore[attr-defined]
            entity_id=ri.entity_id,  # type: ignore[attr-defined]
            field_name=ri.field_name,  # type: ignore[attr-defined]
            raw_value=ri.raw_value,  # type: ignore[attr-defined]
            suggestion=ri.suggestion,  # type: ignore[attr-defined]
            options=[
                ReviewOptionSchema(id=o.id, label=o.label)
                for o in ri.options  # type: ignore[attr-defined]
            ],
            row_data=ri.row_data,  # type: ignore[attr-defined]
        )
        for ri in items
    ]


def _list_item(doc: Document, content: DocumentContent | None = None) -> DocumentListItem:  # noqa: F821
    return DocumentListItem(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        kind=doc.kind,
        row_count=doc.row_count,
        columns=[],
        report_type=doc.report_type,
        chunk_count=doc.chunk_count,
        page_count=doc.page_count,
        tags=doc.tags,
        size_bytes=doc.size_bytes,
        uploaded_at=doc.uploaded_at.isoformat(),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    c: Ctr,
    file: UploadFile = File(...),
    manager: str | None = Form(default=None),
    unit_id: str | None = Form(default=None),
    property_id: str | None = Form(default=None),
    lease_id: str | None = Form(default=None),
    document_type: str | None = Form(default=None),
) -> UploadResponse:
    """Upload a file to the knowledge base.

    Accepts CSV, Excel, PDF, Word, text files, and images. Tabular files
    (CSV/Excel) trigger entity extraction. Other files are stored as
    reference documents and embedded for semantic search.

    Scope params (unit_id, property_id, lease_id, document_type) attach
    the document to specific domain entities in the knowledge graph.
    """
    content = await file.read()
    filename = file.filename or "unknown"
    content_type = (file.content_type or "").lower()

    try:
        result = await c.document_ingest.ingest_upload(
            filename,
            content,
            content_type,
            manager=manager,
            unit_id=unit_id,
            property_id=property_id,
            lease_id=lease_id,
            document_type=document_type,
        )
    except (ValueError, ImportError) as exc:
        raise DomainError(str(exc)) from exc

    doc = result.doc
    review_schemas = _review_items_to_schemas(result.review_items)
    response = UploadResponse(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        kind=doc.kind,
        row_count=doc.row_count,
        columns=[],
        report_type=result.report_type,
        chunk_count=doc.chunk_count,
        page_count=doc.page_count,
        tags=doc.tags,
        size_bytes=doc.size_bytes,
        knowledge=KnowledgeInfo(
            entities_extracted=result.entities_extracted,
            relationships_extracted=result.relationships_extracted,
            ambiguous_rows=result.ambiguous_rows,
            rows_accepted=result.rows_accepted,
            rows_rejected=result.rows_rejected,
            rows_skipped=result.rows_skipped,
            validation_warnings=result.validation_warnings,
            review_items=review_schemas,
        ),
    )

    try:
        await ws_manager.broadcast("ingestion_complete", {
            "document_id": doc.id,
            "filename": doc.filename,
            "kind": doc.kind,
            "report_type": result.report_type,
            "entities_extracted": result.entities_extracted,
            "chunk_count": doc.chunk_count,
            "tags": doc.tags,
        })
    except Exception:
        _log.warning("broadcast_ingestion_failed", exc_info=True)

    return response


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    c: Ctr,
    q: str | None = Query(default=None, description="Filename search"),
    kind: str | None = Query(default=None, description="Filter by kind: tabular, text, image"),
    tags: str | None = Query(default=None, description="Comma-separated tag filter"),
    unit_id: str | None = Query(default=None, description="Filter by unit"),
    property_id: str | None = Query(default=None, description="Filter by property"),
    manager_id: str | None = Query(default=None, description="Filter by manager"),
    sort: str = Query(default="newest", description="Sort: newest, oldest, name"),
    limit: int = Query(default=50, ge=1, le=200),
) -> DocumentListResponse:
    docs = await c.document_resolver.list_documents(
        unit_id=unit_id,
        property_id=property_id,
        manager_id=manager_id,
        kind=kind,
        tags=tags,
        q=q,
        sort=sort,
        limit=limit,
    )
    return DocumentListResponse(documents=[_list_item(d) for d in docs])


@router.get("/tags", response_model=TagsResponse)
async def list_tags(c: Ctr) -> TagsResponse:
    """List all tags in use across documents."""
    return TagsResponse(tags=await c.document_resolver.list_tags())


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str,
    c: Ctr,
) -> DocumentDetail:
    doc = await c.property_store.get_document(document_id)
    if doc is None:
        raise NotFoundError("Document", document_id)
    content = await c.content_store.get(document_id)
    preview = content.rows[:20] if content else []
    columns = content.column_names if content else []
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        kind=doc.kind,
        row_count=doc.row_count,
        columns=columns,
        report_type=doc.report_type,
        chunk_count=doc.chunk_count,
        page_count=doc.page_count,
        tags=doc.tags,
        size_bytes=doc.size_bytes,
        preview=preview,
        uploaded_at=doc.uploaded_at.isoformat(),
    )


@router.get("/{document_id}/rows", response_model=DocumentRowsResponse)
async def query_rows(
    document_id: str,
    c: Ctr,
    limit: int = 100,
) -> DocumentRowsResponse:
    content = await c.content_store.get(document_id)
    if content is None:
        raise NotFoundError("Document", document_id)
    rows = await c.content_store.query_rows(document_id, limit=limit)
    return DocumentRowsResponse(document_id=document_id, rows=rows, count=len(rows))


@router.get("/{document_id}/chunks", response_model=DocumentChunksResponse)
async def query_chunks(
    document_id: str,
    c: Ctr,
    limit: int = 100,
) -> DocumentChunksResponse:
    """Return text chunks for a text document."""
    content = await c.content_store.get(document_id)
    if content is None:
        raise NotFoundError("Document", document_id)
    chunks = [
        ChunkItem(index=c_chunk.index, text=c_chunk.text, page=c_chunk.page)
        for c_chunk in content.chunks[:limit]
    ]
    return DocumentChunksResponse(document_id=document_id, chunks=chunks, count=len(chunks))


@router.patch("/{document_id}/tags", response_model=TagsResponse)
async def update_tags(
    document_id: str,
    c: Ctr,
    body: TagUpdateRequest = Body(...),
) -> TagsResponse:
    """Update tags for a document."""
    updated = await c.content_store.update_tags(document_id, body.tags)
    if not updated:
        raise NotFoundError("Document", document_id)
    return TagsResponse(tags=body.tags)


@router.post("/{document_id}/correct-row", response_model=CorrectRowResponse)
async def correct_row(
    document_id: str,
    c: Ctr,
    body: CorrectRowRequest = Body(...),
) -> CorrectRowResponse:
    """Re-submit a corrected row that was previously rejected or ambiguous.

    The human reviews a rejected row, fixes the problematic field(s), and
    sends it back. The row goes through validation and persistence as if
    it were part of the original upload.
    """
    doc = await c.property_store.get_document(document_id)
    if doc is None:
        raise NotFoundError("Document", document_id)

    content = await c.content_store.get(document_id)
    if content is None:
        raise NotFoundError("Document content", document_id)

    report_type = body.report_type or doc.report_type or "unknown"

    from remi.application.services.ingestion.base import IngestionResult
    from remi.application.services.ingestion.validation import validate_rows

    result = IngestionResult(document_id=document_id)
    result.report_type = report_type
    rows = validate_rows([body.row_data], result)

    if rows:
        ingestion_result = await c.document_ingest._ingestion.ingest_mapped_rows(
            content,
            report_type=report_type,
            rows=rows,
            manager=doc.manager_id,
        )
        return CorrectRowResponse(
            accepted=True,
            entities_created=ingestion_result.entities_created,
            relationships_created=ingestion_result.relationships_created,
            review_items=_review_items_to_schemas(ingestion_result.review_items),
        )

    warnings = [
        f"row {w.row_index} ({w.row_type}).{w.field}: {w.issue}"
        for w in result.validation_warnings
    ]
    return CorrectRowResponse(
        accepted=False,
        validation_warnings=warnings,
        review_items=_review_items_to_schemas(result.review_items),
    )


@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: str,
    c: Ctr,
) -> DeleteResponse:
    deleted = await c.content_store.delete(document_id)
    if not deleted:
        raise NotFoundError("Document", document_id)
    await c.property_store.delete_document(document_id)
    return DeleteResponse(deleted=True, id=document_id)
