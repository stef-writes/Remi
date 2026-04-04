"""remi documents — list, query, and ingest uploaded documents."""

from __future__ import annotations

import asyncio
import contextlib
import json as _json
from pathlib import Path
from typing import Any

import typer

from remi.application.cli import http as _http
from remi.application.cli.shared import get_container, json_out, ser, use_json

cmd = typer.Typer(name="documents", help="List, query, and ingest documents.", no_args_is_help=True)

_CONTENT_TYPES: dict[str, str] = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".pdf": "application/pdf",
}


@cmd.command("ingest")
def ingest(
    file: Path = typer.Argument(..., help="Path to the document file to ingest"),
    manager: str | None = typer.Option(None, "--manager", "-m", help="Manager tag override"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Ingest a document through the LLM extraction pipeline."""
    if not file.exists():
        typer.echo(f"File not found: {file}", err=True)
        raise typer.Exit(1)
    asyncio.run(_ingest(file, manager, use_json(json_output)))


async def _ingest(file: Path, manager: str | None, fmt_json: bool) -> None:
    content = file.read_bytes()
    content_type = _CONTENT_TYPES.get(file.suffix.lower(), "application/octet-stream")

    container = get_container()
    await container.ensure_bootstrapped()

    result = await container.document_ingest.ingest_upload(
        file.name,
        content,
        content_type,
        manager=manager,
    )

    if fmt_json:
        json_out(
            {
                "doc_id": result.doc.id,
                "filename": result.doc.filename,
                "report_type": result.report_type,
                "entities_extracted": result.entities_extracted,
                "relationships_extracted": result.relationships_extracted,
                "signals_produced": result.signals_produced,
                "pipeline_warnings": result.pipeline_warnings,
            }
        )
    else:
        typer.echo(f"\nIngested: {result.doc.filename}")
        typer.echo(f"  Report type:    {result.report_type}")
        typer.echo(f"  Entities:       {result.entities_extracted}")
        typer.echo(f"  Relationships:  {result.relationships_extracted}")
        typer.echo(f"  Signals:        {result.signals_produced}")
        if result.pipeline_warnings:
            typer.echo(f"  Warnings: {', '.join(result.pipeline_warnings)}", err=True)


@cmd.command("list")
def list_documents(
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """List all uploaded documents with metadata."""
    asyncio.run(_list_documents(use_json(json_output)))


async def _list_documents(fmt_json: bool) -> None:
    if _http.is_sandbox():
        data = _http.get("/documents")
        items = data.get("documents", [])
        if fmt_json:
            json_out({"count": len(items), "documents": items})
        else:
            if not items:
                typer.echo("No documents uploaded.")
                return
            typer.echo(f"\n{len(items)} documents:\n")
            for d in items:
                typer.echo(
                    f"  {d.get('id', '?'):12s}  "
                    f"{d.get('filename', '?'):30s}  "
                    f"{d.get('row_count', 0)} rows"
                )
        return

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
            typer.echo(
                f"  {d['id']:12s}  {d['filename']:30s}  "
                f"{d['row_count']} rows  {len(d['columns'])} cols"
            )


@cmd.command("query")
def query(
    doc_id: str | None = typer.Option(None, "--doc-id", "-d", help="Specific document ID"),
    query_text: str | None = typer.Option(
        None, "--query", "-q", help="Text search across all values"
    ),
    filters: str | None = typer.Option(
        None, "--filters", "-f", help='Column filters as JSON, e.g. \'{"status": "vacant"}\''
    ),
    limit: int = typer.Option(50, "--limit", "-l", help="Max rows to return"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Search uploaded document rows by text, filters, or document ID."""
    parsed_filters: dict[str, Any] = {}
    if filters:
        with contextlib.suppress(_json.JSONDecodeError, TypeError):
            parsed_filters = _json.loads(filters)
    asyncio.run(_query(doc_id, query_text, parsed_filters, limit, use_json(json_output)))


async def _query(
    doc_id: str | None,
    query_text: str | None,
    filters: dict[str, Any],
    limit: int,
    fmt_json: bool,
) -> None:
    if _http.is_sandbox():
        if doc_id:
            data = _http.get(f"/documents/{doc_id}/rows?limit={limit}")
        else:
            data = _http.get(f"/documents/query?limit={limit}")
        if fmt_json:
            json_out(data)
        else:
            rows = data.get("rows", [])
            typer.echo(f"\n{len(rows)} rows returned")
            for row in rows[:20]:
                typer.echo(f"  {row}")
        return

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
            all_rows: list[dict[str, Any]] = []
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
