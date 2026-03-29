"""Document tools — in-process calls to DocumentStore.

Provides: document_list, document_query.
"""

from __future__ import annotations

from typing import Any

from remi.domain.documents.models import DocumentStore
from remi.domain.tools.ports import ToolArg, ToolDefinition, ToolRegistry


def register_document_tools(
    registry: ToolRegistry,
    *,
    document_store: DocumentStore,
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
            description="List all uploaded documents with metadata (filename, columns, row count, upload date).",
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
            docs = [await store.get(doc_id)]
            docs = [d for d in docs if d is not None]
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
            all_rows = [
                r for r in all_rows
                if any(q_lower in str(v).lower() for v in r.values())
            ]

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
                'value or a list for IN-style matching, e.g. {"property_name": ["Oak Tower", "Elm Place"]}.'
            ),
            args=[
                ToolArg(name="document_id", description="Specific document ID (omit to search all)"),
                ToolArg(name="query", description="Text search across all column values"),
                ToolArg(name="filters", description='Column filters as JSON object. Values can be a string or a list of strings for IN-style matching.', type="object"),
                ToolArg(name="limit", description="Max rows to return (default: 50)", type="integer"),
            ],
        ),
    )
