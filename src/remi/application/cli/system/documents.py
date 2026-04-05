"""``remi documents`` — CLI commands for document management.

Ingest reports, list documents, preview rows/chunks, and manage tags.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

cmd = typer.Typer(name="documents", help="Document upload, ingestion, and listing.")


def _truncate(text: str, max_len: int = 80) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


async def _ingest(
    filepath: str,
    manager: str | None,
    unit_id: str | None,
    property_id: str | None,
    lease_id: str | None,
    document_type: str | None,
    no_embed: bool,
) -> None:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    ingest = container.document_ingest

    path = Path(filepath).expanduser()
    if not path.exists():
        typer.echo(f"File not found: {path}", err=True)
        raise typer.Exit(1)

    ct_map = {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".md": "text/markdown",
    }
    content_type = ct_map.get(path.suffix.lower(), "application/octet-stream")
    content = path.read_bytes()

    typer.echo(f"Ingesting {path.name}...")
    result = await ingest.ingest_upload(
        path.name,
        content,
        content_type,
        manager=manager,
        unit_id=unit_id,
        property_id=property_id,
        lease_id=lease_id,
        document_type=document_type,
        run_pipelines=not no_embed,
    )

    typer.echo(f"  doc_id:        {result.doc.id}")
    typer.echo(f"  report_type:   {result.report_type}")
    typer.echo(f"  entities:      {result.entities_extracted}")
    typer.echo(f"  relationships: {result.relationships_extracted}")
    typer.echo(f"  rows_accepted: {result.rows_accepted}")
    typer.echo(f"  rows_rejected: {result.rows_rejected}")
    if result.validation_warnings:
        typer.echo("  warnings:")
        for w in result.validation_warnings[:10]:
            typer.echo(f"    - {_truncate(w, 120)}")
    if result.pipeline_warnings:
        typer.echo("  pipeline_warnings:")
        for w in result.pipeline_warnings:
            typer.echo(f"    - {_truncate(w, 120)}")
    typer.echo(f"  embedded:      {result.entities_embedded}")


async def _list_docs(
    kind: str | None,
    manager_id: str | None,
    limit: int,
) -> None:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    ps = container.property_store

    docs = await ps.list_documents(manager_id=manager_id)

    if kind:
        docs = [d for d in docs if d.kind == kind]

    docs.sort(key=lambda d: d.uploaded_at, reverse=True)
    docs = docs[:limit]

    if not docs:
        typer.echo("No documents found.")
        return

    for d in docs:
        tag_str = ", ".join(d.tags) if d.tags else ""
        scope_parts: list[str] = []
        if d.manager_id:
            scope_parts.append(f"mgr:{d.manager_id[:8]}")
        if d.property_id:
            scope_parts.append(f"prop:{d.property_id[:8]}")
        if d.unit_id:
            scope_parts.append(f"unit:{d.unit_id[:8]}")
        scope_str = " | ".join(scope_parts) if scope_parts else ""

        typer.echo(
            f"  {d.id[:12]}  {d.kind:<8}  {d.document_type.value:<16}  "
            f"rows={d.row_count:<5}  chunks={d.chunk_count:<4}  "
            f"{_truncate(d.filename, 40)}"
        )
        if scope_str:
            typer.echo(f"             scope: {scope_str}")
        if tag_str:
            typer.echo(f"             tags: {tag_str}")


async def _preview(doc_id: str, limit: int) -> None:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    cs = container.content_store

    content = await cs.get(doc_id)
    if content is None:
        typer.echo(f"Document not found: {doc_id}", err=True)
        raise typer.Exit(1)

    if content.kind.value == "tabular":
        typer.echo(f"Columns: {content.column_names}")
        typer.echo(f"Rows ({content.row_count} total, showing first {limit}):")
        for i, row in enumerate(content.rows[:limit]):
            typer.echo(f"  [{i}] {row}")
    elif content.kind.value == "text":
        typer.echo(f"Chunks ({len(content.chunks)} total, showing first {limit}):")
        for chunk in content.chunks[:limit]:
            page_str = f" (page {chunk.page})" if chunk.page is not None else ""
            typer.echo(f"  [{chunk.index}]{page_str} {_truncate(chunk.text, 200)}")
    else:
        typer.echo(f"  kind: {content.kind.value}")
        typer.echo(f"  size: {content.size_bytes} bytes")


async def _delete(doc_id: str) -> None:
    from remi.application.cli.shared import get_container_async

    container = await get_container_async()
    cs = container.content_store
    ps = container.property_store

    deleted = await cs.delete(doc_id)
    if deleted:
        await ps.delete_document(doc_id)
        typer.echo(f"Deleted: {doc_id}")
    else:
        typer.echo(f"Not found: {doc_id}", err=True)
        raise typer.Exit(1)


@cmd.command()
def ingest(
    filepath: str = typer.Argument(..., help="Path to file to ingest"),
    manager: str | None = typer.Option(None, "--manager", "-m", help="Manager tag"),
    unit_id: str | None = typer.Option(None, "--unit", help="Unit to scope to"),
    property_id: str | None = typer.Option(None, "--property", help="Property to scope to"),
    lease_id: str | None = typer.Option(None, "--lease", help="Lease to scope to"),
    document_type: str | None = typer.Option(
        None, "--type", help="Document type (lease, report, etc.)",
    ),
    no_embed: bool = typer.Option(False, "--no-embed", help="Skip embedding pipeline"),
) -> None:
    """Ingest a file into the knowledge base."""
    asyncio.run(_ingest(filepath, manager, unit_id, property_id, lease_id, document_type, no_embed))


@cmd.command("list")
def list_docs(
    kind: str | None = typer.Option(None, "--kind", "-k", help="Filter by kind"),
    manager_id: str | None = typer.Option(None, "--manager-id", help="Filter by manager"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max documents to show"),
) -> None:
    """List documents in the knowledge base."""
    asyncio.run(_list_docs(kind, manager_id, limit))


@cmd.command()
def preview(
    doc_id: str = typer.Argument(..., help="Document ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows/chunks to show"),
) -> None:
    """Preview rows or chunks from a document."""
    asyncio.run(_preview(doc_id, limit))


@cmd.command()
def delete(
    doc_id: str = typer.Argument(..., help="Document ID to delete"),
) -> None:
    """Delete a document from the knowledge base."""
    asyncio.run(_delete(doc_id))
