"""Document tools — in-process calls to DocumentStore and ingestion pipeline.

Provides: document_list, document_query, ingest_document.
"""

from __future__ import annotations

from typing import Any

from remi.agent.types import ToolArg, ToolDefinition, ToolRegistry
from remi.agent.documents.types import DocumentStore
from remi.application.services.ingestion.pipeline import DocumentIngestService


def register_document_tools(
    registry: ToolRegistry,
    *,
    document_store: DocumentStore,
    document_ingest: DocumentIngestService | None = None,
) -> None:
    store = document_store

    # -- document_list ---------------------------------------------------------

    async def document_list(args: dict[str, Any]) -> Any:
        docs = await store.list_documents()
        return [
            {
                "id": d.id,
                "filename": d.filename,
                "columns": d.column_names,
                "row_count": d.row_count,
                "uploaded_at": d.uploaded_at.isoformat(),
                "report_type": d.metadata.get("report_type"),
            }
            for d in docs
        ]

    registry.register(
        "document_list",
        document_list,
        ToolDefinition(
            name="document_list",
            description=(
                "List all uploaded documents with metadata "
                "(filename, columns, row count, upload date)."
            ),
            args=[],
        ),
    )

    # -- document_query --------------------------------------------------------

    async def document_query(args: dict[str, Any]) -> Any:
        doc_id = args.get("document_id")
        query = args.get("query")
        filters = args.get("filters")
        limit = int(args.get("limit", 50))

        if doc_id:
            maybe = await store.get(doc_id)
            docs = [maybe] if maybe is not None else []
        else:
            docs = await store.list_documents()

        if not docs:
            return {"rows": [], "total": 0}

        all_rows: list[dict[str, Any]] = []
        for doc in docs:
            rows = await store.query_rows(doc.id, filters=filters, limit=limit * 2)
            for row in rows:
                row["_document_id"] = doc.id
                row["_filename"] = doc.filename
            all_rows.extend(rows)

        if query:
            q_lower = query.lower()
            all_rows = [r for r in all_rows if any(q_lower in str(v).lower() for v in r.values())]

        result = all_rows[:limit]
        return {"rows": result, "total": len(result)}

    registry.register(
        "document_query",
        document_query,
        ToolDefinition(
            name="document_query",
            description=(
                "Search uploaded document rows. Can filter by document_id, text query "
                "across all values, or column filters. Filter values can be a single "
                "value or a list for IN-style matching, e.g. "
                '{"property_name": ["100 Smithfield St", "1002 Fordham Ave"]}.'
            ),
            args=[
                ToolArg(
                    name="document_id", description="Specific document ID (omit to search all)"
                ),
                ToolArg(name="query", description="Text search across all column values"),
                ToolArg(
                    name="filters",
                    description=(
                        "Column filters as JSON object. "
                        "Values can be a string or a list of strings for IN-style matching."
                    ),
                    type="object",
                ),
                ToolArg(
                    name="limit", description="Max rows to return (default: 50)", type="integer"
                ),
            ],
        ),
    )

    # -- ingest_document -------------------------------------------------------
    # Only registered when the ingestion service is available (API context).

    if document_ingest is not None:
        ingest = document_ingest

        async def ingest_document(args: dict[str, Any]) -> Any:
            import aiofiles

            file_path = args.get("file_path", "")
            manager = args.get("manager")

            try:
                async with aiofiles.open(file_path, "rb") as f:
                    content = await f.read()
            except (OSError, FileNotFoundError) as exc:
                return {"error": f"Cannot read file: {exc}"}

            from pathlib import Path as _Path

            suffix = _Path(file_path).suffix.lower()
            _ct_map = {
                ".csv": "text/csv",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xls": "application/vnd.ms-excel",
                ".pdf": "application/pdf",
            }
            content_type = _ct_map.get(suffix, "application/octet-stream")
            filename = _Path(file_path).name

            result = await ingest.ingest_upload(filename, content, content_type, manager=manager)
            return {
                "doc_id": result.doc.id,
                "filename": result.doc.filename,
                "report_type": result.report_type,
                "entities_extracted": result.entities_extracted,
                "relationships_extracted": result.relationships_extracted,
                "signals_produced": result.signals_produced,
                "pipeline_warnings": result.pipeline_warnings,
            }

        registry.register(
            "ingest_document",
            ingest_document,
            ToolDefinition(
                name="ingest_document",
                description=(
                    "Ingest a document file through the LLM extraction pipeline. "
                    "Classifies the report type, extracts all rows into domain entities, "
                    "enriches unknown rows, and runs the signal pipeline. "
                    "Use this when a new report file is available and needs to be processed."
                ),
                args=[
                    ToolArg(
                        name="file_path",
                        description="Absolute path to the document file to ingest",
                        required=True,
                    ),
                    ToolArg(
                        name="manager",
                        description="Optional manager tag to associate with the document",
                    ),
                ],
            ),
        )
