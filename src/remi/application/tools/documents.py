"""Document tools — in-process calls to ContentStore and ingestion pipeline.

Provides: document_list, document_query, document_search, ingest_document.
"""

from __future__ import annotations

from typing import Any

import structlog

from remi.agent.documents import ContentStore
from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry
from remi.application.core.protocols import PropertyStore, VectorSearch
from remi.application.services.ingestion.pipeline import DocumentIngestService

_log = structlog.get_logger(__name__)


class DocumentToolProvider(ToolProvider):
    def __init__(
        self,
        content_store: ContentStore,
        property_store: PropertyStore,
        document_ingest: DocumentIngestService | None = None,
        vector_search: VectorSearch | None = None,
    ) -> None:
        self._content_store = content_store
        self._property_store = property_store
        self._document_ingest = document_ingest
        self._vector_search = vector_search

    def register(self, registry: ToolRegistry) -> None:
        cs = self._content_store
        ps = self._property_store

        # -- document_list ---------------------------------------------------------

        async def document_list(args: dict[str, Any]) -> Any:
            unit_id = args.get("unit_id")
            property_id = args.get("property_id")
            manager_id = args.get("manager_id")
            docs = await ps.list_documents(
                unit_id=unit_id,
                property_id=property_id,
                manager_id=manager_id,
            )
            return [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "kind": d.kind,
                    "document_type": d.document_type.value,
                    "row_count": d.row_count,
                    "chunk_count": d.chunk_count,
                    "page_count": d.page_count,
                    "tags": d.tags,
                    "uploaded_at": d.uploaded_at.isoformat(),
                    "report_type": d.report_type,
                    "unit_id": d.unit_id,
                    "property_id": d.property_id,
                    "manager_id": d.manager_id,
                    "lease_id": d.lease_id,
                }
                for d in docs
            ]

        registry.register(
            "document_list",
            document_list,
            ToolDefinition(
                name="document_list",
                description=(
                    "List documents in the knowledge base with metadata. "
                    "Filter by unit_id, property_id, or manager_id to scope results."
                ),
                args=[
                    ToolArg(name="unit_id", description="Filter by unit"),
                    ToolArg(name="property_id", description="Filter by property"),
                    ToolArg(name="manager_id", description="Filter by manager"),
                ],
            ),
        )

        # -- document_query --------------------------------------------------------

        async def document_query(args: dict[str, Any]) -> Any:
            doc_id = args.get("document_id")
            query = args.get("query")
            filters = args.get("filters")
            limit = int(args.get("limit", 50))

            if doc_id:
                maybe = await cs.get(doc_id)
                contents = [maybe] if maybe is not None else []
            else:
                contents = await cs.list_documents()

            if not contents:
                return {"rows": [], "chunks": [], "total": 0}

            all_rows: list[dict[str, Any]] = []
            all_chunks: list[dict[str, Any]] = []

            for content in contents:
                if content.kind.value == "tabular":
                    rows = await cs.query_rows(content.id, filters=filters, limit=limit * 2)
                    for row in rows:
                        row["_document_id"] = content.id
                        row["_filename"] = content.filename
                    all_rows.extend(rows)
                elif content.kind.value == "text":
                    for chunk in content.chunks[:limit * 2]:
                        entry: dict[str, Any] = {
                            "_document_id": content.id,
                            "_filename": content.filename,
                            "chunk_index": chunk.index,
                            "page": chunk.page,
                            "text": chunk.text,
                        }
                        all_chunks.append(entry)

            if query:
                q_lower = query.lower()
                all_rows = [
                    r
                    for r in all_rows
                    if any(q_lower in str(v).lower() for v in r.values())
                ]
                all_chunks = [
                    c for c in all_chunks
                    if q_lower in c.get("text", "").lower()
                ]

            return {
                "rows": all_rows[:limit],
                "chunks": all_chunks[:limit],
                "total": len(all_rows) + len(all_chunks),
            }

        registry.register(
            "document_query",
            document_query,
            ToolDefinition(
                name="document_query",
                description=(
                    "Search knowledge base documents. For tabular docs (reports), searches rows. "
                    "For text docs (PDFs, contracts), searches text chunks. "
                    "Can filter by document_id, text query, or column filters."
                ),
                args=[
                    ToolArg(
                        name="document_id", description="Specific document ID (omit to search all)"
                    ),
                    ToolArg(name="query", description="Text search across content"),
                    ToolArg(
                        name="filters",
                        description="Column filters (tabular docs only) as JSON object.",
                        type="object",
                    ),
                    ToolArg(
                        name="limit", description="Max results to return (default: 50)",
                        type="integer",
                    ),
                ],
            ),
        )

        # -- document_search -------------------------------------------------------

        if self._vector_search is not None:
            vs = self._vector_search

            async def document_search(args: dict[str, Any]) -> Any:
                query = args.get("query", "")
                limit = int(args.get("limit", 10))
                unit_id = args.get("unit_id")
                property_id = args.get("property_id")
                if not query.strip():
                    return {"results": [], "total": 0}

                metadata_filter: dict[str, Any] | None = None
                if unit_id or property_id:
                    metadata_filter = {}
                    if unit_id:
                        metadata_filter["unit_id"] = unit_id
                    if property_id:
                        metadata_filter["property_id"] = property_id

                results = await vs.semantic_search(
                    query,
                    limit=limit,
                    min_score=0.25,
                    metadata_filter=metadata_filter,
                )

                doc_types = {"DocumentRow", "DocumentChunk"}
                hits = [
                    {
                        "entity_id": r.entity_id,
                        "entity_type": r.entity_type,
                        "text": r.text[:500],
                        "score": round(r.score, 3),
                        "filename": r.metadata.get("filename", ""),
                        "page": r.metadata.get("page"),
                        "document_id": r.metadata.get("document_id", ""),
                    }
                    for r in results
                    if r.entity_type in doc_types
                ]
                return {"results": hits, "total": len(hits)}

            registry.register(
                "document_search",
                document_search,
                ToolDefinition(
                    name="document_search",
                    description=(
                        "Semantic search across knowledge base documents. "
                        "Finds relevant passages from PDFs, contracts, reports, and other "
                        "uploaded files using vector similarity. Filter by unit_id or "
                        "property_id to scope results."
                    ),
                    args=[
                        ToolArg(
                            name="query",
                            description="Natural language search query",
                            required=True,
                        ),
                        ToolArg(name="unit_id", description="Scope to a specific unit"),
                        ToolArg(name="property_id", description="Scope to a specific property"),
                        ToolArg(
                            name="limit",
                            description="Max results (default: 10)",
                            type="integer",
                        ),
                    ],
                ),
            )

        # -- ingest_document -------------------------------------------------------

        if self._document_ingest is not None:
            ingest = self._document_ingest

            async def ingest_document(args: dict[str, Any]) -> Any:
                import aiofiles

                file_path = args.get("file_path", "")
                manager = args.get("manager")
                unit_id = args.get("unit_id")
                property_id = args.get("property_id")
                lease_id = args.get("lease_id")
                document_type = args.get("document_type")

                try:
                    async with aiofiles.open(file_path, "rb") as f:
                        content = await f.read()
                except (OSError, FileNotFoundError) as exc:
                    _log.warning(
                        "ingest_document_file_error",
                        file_path=file_path,
                        exc_info=True,
                    )
                    return {"error": f"Cannot read file: {exc}"}

                from pathlib import Path as _Path

                suffix = _Path(file_path).suffix.lower()
                _ct_map = {
                    ".csv": "text/csv",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".xls": "application/vnd.ms-excel",
                    ".pdf": "application/pdf",
                    ".docx": (
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                    ".txt": "text/plain",
                    ".md": "text/markdown",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }
                content_type = _ct_map.get(suffix, "application/octet-stream")
                filename = _Path(file_path).name

                result = await ingest.ingest_upload(
                    filename, content, content_type,
                    manager=manager,
                    unit_id=unit_id,
                    property_id=property_id,
                    lease_id=lease_id,
                    document_type=document_type,
                )
                return {
                    "doc_id": result.doc.id,
                    "filename": result.doc.filename,
                    "report_type": result.report_type,
                    "entities_extracted": result.entities_extracted,
                    "relationships_extracted": result.relationships_extracted,
                    "pipeline_warnings": result.pipeline_warnings,
                }

            registry.register(
                "ingest_document",
                ingest_document,
                ToolDefinition(
                    name="ingest_document",
                    description=(
                        "Ingest a document file through the extraction pipeline. "
                        "Classifies the report type, extracts entities, and runs embedding. "
                        "Scope params attach the document to domain entities in the graph."
                    ),
                    args=[
                        ToolArg(
                            name="file_path",
                            description="Absolute path to the document file to ingest",
                            required=True,
                        ),
                        ToolArg(name="manager", description="Manager tag to associate"),
                        ToolArg(name="unit_id", description="Unit to scope the document to"),
                        ToolArg(
                            name="property_id",
                            description="Property to scope the document to",
                        ),
                        ToolArg(
                            name="lease_id",
                            description="Lease this document evidences",
                        ),
                        ToolArg(
                            name="document_type",
                            description="Type: lease, amendment, notice, report, "
                            "inspection, correspondence, other",
                        ),
                    ],
                ),
            )
