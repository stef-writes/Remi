"""remi documents — list and query uploaded documents."""

from __future__ import annotations

import asyncio
import json as _json

import typer

from remi.interfaces.cli.shared import get_container, json_out, ser, use_json

cmd = typer.Typer(name="documents", help="List and query uploaded documents.", no_args_is_help=True)


@cmd.command("list")
def list_documents(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List all uploaded documents with metadata."""
    asyncio.run(_list_documents(use_json(json_output)))


async def _list_documents(fmt_json: bool) -> None:
    container = get_container()
    docs = await container.document_store.list_documents()
    items = [
        {
            "id": d.id,
            "filename": d.filename,
            "content_type": d.content_type,
            "row_count": d.row_count,
            "columns": d.column_names,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
    ]

    if fmt_json:
        json_out({"count": len(items), "documents": items})
    else:
        if not items:
            typer.echo("No documents uploaded.")
            return
        typer.echo(f"\n{len(items)} documents:\n")
        for d in items:
            typer.echo(f"  {d['id']:12s}  {d['filename']:30s}  {d['row_count']} rows  {len(d['columns'])} cols")


@cmd.command("query")
def query(
    doc_id: str | None = typer.Option(None, "--doc-id", "-d", help="Specific document ID"),
    query_text: str | None = typer.Option(None, "--query", "-q", help="Text search across all values"),
    filters: str | None = typer.Option(None, "--filters", "-f", help='Column filters as JSON, e.g. \'{"status": "vacant"}\''),
    limit: int = typer.Option(50, "--limit", "-l", help="Max rows to return"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search uploaded document rows by text, filters, or document ID."""
    parsed_filters: dict = {}
    if filters:
        try:
            parsed_filters = _json.loads(filters)
        except (_json.JSONDecodeError, TypeError):
            pass
    asyncio.run(_query(doc_id, query_text, parsed_filters, limit, use_json(json_output)))


async def _query(
    doc_id: str | None,
    query_text: str | None,
    filters: dict,
    limit: int,
    fmt_json: bool,
) -> None:
    container = get_container()
    store = container.document_store

    if doc_id:
        rows = await store.query_rows(doc_id, filters=filters or None, limit=limit)
        data = {"document_id": doc_id, "count": len(rows), "rows": ser(rows)}
    else:
        docs = await store.list_documents()
        if not docs:
            data = {"count": 0, "rows": [], "message": "No documents uploaded yet."}
        else:
            all_rows: list[dict] = []
            for d in docs:
                rows = await store.query_rows(d.id, filters=filters or None, limit=limit)
                if query_text:
                    q = query_text.lower()
                    rows = [r for r in rows if any(q in str(v).lower() for v in r.values())]
                for r in rows:
                    r["__source_doc"] = d.filename
                    r["__doc_id"] = d.id
                all_rows.extend(rows)
                if len(all_rows) >= limit:
                    break
            data = {"count": len(all_rows[:limit]), "rows": ser(all_rows[:limit])}

    if fmt_json:
        json_out(data)
    else:
        typer.echo(f"\n{data['count']} rows returned")
        for row in data.get("rows", [])[:20]:
            typer.echo(f"  {row}")
