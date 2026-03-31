"""Document upload and query REST endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from remi.interfaces.api.dependencies import get_container
from remi.interfaces.api.documents.schemas import (
    DeleteResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentRowsResponse,
    KnowledgeInfo,
    UploadResponse,
)

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    manager: str | None = Form(default=None),
    container: Container = Depends(get_container),
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
        result = await container.document_ingest.ingest_upload(
            filename, content, content_type, manager=manager,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
        ),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    container: Container = Depends(get_container),
) -> DocumentListResponse:
    docs = await container.document_store.list_documents()
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
    container: Container = Depends(get_container),
) -> DocumentDetail:
    doc = await container.document_store.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
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
    container: Container = Depends(get_container),
) -> DocumentRowsResponse:
    doc = await container.document_store.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    rows = await container.document_store.query_rows(document_id, limit=limit)
    return DocumentRowsResponse(document_id=document_id, rows=rows, count=len(rows))


@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(
    document_id: str,
    container: Container = Depends(get_container),
) -> DeleteResponse:
    deleted = await container.document_store.delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return DeleteResponse(deleted=True, id=document_id)
