"""Document upload and query REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from remi.agent.documents.types import DocumentStore
from remi.application.services.ingestion.pipeline import DocumentIngestService
from remi.application.api.document_schemas import (
    DeleteResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentRowsResponse,
    KnowledgeInfo,
    UploadResponse,
)
from remi.application.api.dependencies import get_document_ingest, get_document_store
from remi.types.errors import DomainError, NotFoundError

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    manager: str | None = Form(default=None),
    ingest: DocumentIngestService = Depends(get_document_ingest),
) -> UploadResponse:
    """Upload a report.

    When uploading a per-manager report, pass ``manager`` with the property
    manager's name (e.g. "Liam Martin Management").  Every property in the
    file will be assigned to that manager.  When uploading a bulk report that
    already contains manager Tags (lease expiration), ``manager`` can be
    omitted — the Tags column will be used instead.
    """
    content = await file.read()
    filename = file.filename or "unknown"
    content_type = (file.content_type or "").lower()

    try:
        result = await ingest.ingest_upload(
            filename,
            content,
            content_type,
            manager=manager,
        )
    except ValueError as exc:
        raise DomainError(str(exc)) from exc

    return UploadResponse(
        id=result.doc.id,
        filename=result.doc.filename,
        content_type=result.doc.content_type,
        row_count=result.doc.row_count,
        columns=result.doc.column_names,
        report_type=result.report_type,
        knowledge=KnowledgeInfo(
            entities_extracted=result.entities_extracted,
            relationships_extracted=result.relationships_extracted,
            ambiguous_rows=result.ambiguous_rows,
            rows_accepted=result.rows_accepted,
            rows_rejected=result.rows_rejected,
            rows_skipped=result.rows_skipped,
            validation_warnings=result.validation_warnings,
        ),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    ds: DocumentStore = Depends(get_document_store),
) -> DocumentListResponse:
    docs = await ds.list_documents()
    return DocumentListResponse(
        documents=[
            DocumentListItem(
                id=d.id,
                filename=d.filename,
                content_type=d.content_type,
                row_count=d.row_count,
                columns=d.column_names,
                report_type=d.metadata.get("report_type", "unknown"),
                uploaded_at=d.uploaded_at.isoformat(),
            )
            for d in docs
        ],
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str,
    ds: DocumentStore = Depends(get_document_store),
) -> DocumentDetail:
    doc = await ds.get(document_id)
    if doc is None:
        raise NotFoundError("Document", document_id)
    return DocumentDetail(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        row_count=doc.row_count,
        columns=doc.column_names,
        report_type=doc.metadata.get("report_type", "unknown"),
        preview=doc.rows[:20],
        uploaded_at=doc.uploaded_at.isoformat(),
    )


@router.get("/{document_id}/rows", response_model=DocumentRowsResponse)
async def query_rows(
    document_id: str,
    limit: int = 100,
    ds: DocumentStore = Depends(get_document_store),
) -> DocumentRowsResponse:
    doc = await ds.get(document_id)
    if doc is None:
        raise NotFoundError("Document", document_id)
    rows = await ds.query_rows(document_id, limit=limit)
    return DocumentRowsResponse(document_id=document_id, rows=rows, count=len(rows))


@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: str,
    ds: DocumentStore = Depends(get_document_store),
) -> DeleteResponse:
    deleted = await ds.delete(document_id)
    if not deleted:
        raise NotFoundError("Document", document_id)
    return DeleteResponse(deleted=True, id=document_id)
