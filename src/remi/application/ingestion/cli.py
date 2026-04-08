"""Ingestion CLI — document upload, listing, and search."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from remi.shell.cli.output import emit_error, emit_success

cli_group = typer.Typer(name="ingestion", help="Document ingestion commands.")


def _container():  # noqa: ANN202
    from remi.shell.config.container import Container

    return Container()


@cli_group.command()
def upload(
    file: Path = typer.Argument(help="Path to document file"),
    manager: str | None = typer.Option(None, help="Manager name or ID"),
    property_id: str | None = typer.Option(None, help="Property ID"),
    document_type: str | None = typer.Option(None, help="Document type hint"),
) -> None:
    """Upload and ingest a document."""
    if not file.exists():
        emit_error(
            "FILE_NOT_FOUND",
            f"File not found: {file}",
            command="remi ingestion upload",
        )

    content = file.read_bytes()
    content_type = _guess_content_type(file)

    c = _container()
    result = asyncio.run(
        c.document_ingest.ingest_upload(
            filename=file.name,
            content=content,
            content_type=content_type,
            manager=manager,
            property_id=property_id,
            document_type=document_type,
        )
    )
    emit_success(result.model_dump(mode="json"), command="remi ingestion upload")


@cli_group.command()
def documents(
    manager_id: str | None = typer.Option(None, help="Filter by manager ID"),
    property_id: str | None = typer.Option(None, help="Filter by property ID"),
) -> None:
    """List ingested documents."""
    c = _container()
    if manager_id or property_id:
        docs = asyncio.run(c.property_store.list_documents(
            manager_id=manager_id, property_id=property_id,
        ))
    else:
        docs = asyncio.run(c.content_store.list_documents())

    emit_success(
        [d.model_dump(mode="json") for d in docs] if docs else [],
        command="remi ingestion documents",
    )


@cli_group.command(name="document-search")
def document_search(
    query: str = typer.Argument(help="Search query"),
    property_id: str | None = typer.Option(None, help="Filter by property"),
    limit: int = typer.Option(10, help="Max results"),
) -> None:
    """Semantic search across document content."""
    c = _container()
    results = asyncio.run(c.search_service.search(query))
    emit_success(
        [r.model_dump(mode="json") for r in results],
        command="remi ingestion document-search",
    )


def _guess_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".json": "application/json",
    }.get(suffix, "application/octet-stream")
