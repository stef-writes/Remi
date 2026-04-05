"""Response schemas for document endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReviewOptionSchema(BaseModel):
    id: str
    label: str


class ReviewItemSchema(BaseModel):
    kind: str
    severity: str
    message: str
    row_index: int | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    field_name: str | None = None
    raw_value: str | None = None
    suggestion: str | None = None
    options: list[ReviewOptionSchema] = []
    row_data: dict[str, Any] | None = None


class KnowledgeInfo(BaseModel):
    entities_extracted: int
    relationships_extracted: int
    ambiguous_rows: int
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_skipped: int = 0
    validation_warnings: list[str] = []
    review_items: list[ReviewItemSchema] = []


class UploadResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    kind: str = "tabular"
    row_count: int
    columns: list[str]
    report_type: str
    chunk_count: int = 0
    page_count: int = 0
    tags: list[str] = []
    size_bytes: int = 0
    knowledge: KnowledgeInfo


class DocumentListItem(BaseModel):
    id: str
    filename: str
    content_type: str
    kind: str = "tabular"
    row_count: int
    columns: list[str]
    report_type: str
    chunk_count: int = 0
    page_count: int = 0
    tags: list[str] = []
    size_bytes: int = 0
    uploaded_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]


class ChunkItem(BaseModel):
    index: int
    text: str
    page: int | None = None


class DocumentDetail(BaseModel):
    id: str
    filename: str
    content_type: str
    kind: str = "tabular"
    row_count: int
    columns: list[str]
    report_type: str
    chunk_count: int = 0
    page_count: int = 0
    tags: list[str] = []
    size_bytes: int = 0
    preview: list[dict[str, Any]] = Field(default_factory=list)
    uploaded_at: str


class DocumentRowsResponse(BaseModel):
    document_id: str
    rows: list[dict[str, Any]]
    count: int


class DocumentChunksResponse(BaseModel):
    document_id: str
    chunks: list[ChunkItem]
    count: int


class TagsResponse(BaseModel):
    tags: list[str]


class TagUpdateRequest(BaseModel):
    tags: list[str]


class CorrectRowRequest(BaseModel):
    """A corrected row resubmitted by the human for re-ingestion."""

    row_data: dict[str, Any]
    report_type: str | None = None


class CorrectRowResponse(BaseModel):
    accepted: bool
    entities_created: int = 0
    relationships_created: int = 0
    review_items: list[ReviewItemSchema] = []
    validation_warnings: list[str] = []


class DeleteResponse(BaseModel):
    deleted: bool
    id: str
