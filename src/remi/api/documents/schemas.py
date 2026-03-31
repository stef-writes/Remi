"""Response schemas for document endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class KnowledgeInfo(BaseModel):
    entities_extracted: int
    relationships_extracted: int
    ambiguous_rows: int


class UploadResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    row_count: int
    columns: list[str]
    report_type: str
    knowledge: KnowledgeInfo


class DocumentListItem(BaseModel):
    id: str
    filename: str
    content_type: str
    row_count: int
    columns: list[str]
    report_type: str
    uploaded_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]


class DocumentDetail(BaseModel):
    id: str
    filename: str
    content_type: str
    row_count: int
    columns: list[str]
    report_type: str
    preview: list[dict[str, Any]]
    uploaded_at: str


class DocumentRowsResponse(BaseModel):
    document_id: str
    rows: list[dict[str, Any]]
    count: int


class DeleteResponse(BaseModel):
    deleted: bool
    id: str
