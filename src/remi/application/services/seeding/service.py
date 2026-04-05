"""PortfolioLoader — bulk-ingest AppFolio report exports.

Loads a directory of reports in two passes:
  1. property_directory files first — establishes managers, portfolios,
     and properties so that all subsequent reports resolve portfolio_id inline.
  2. all other tabular and reference files second.

After both passes, runs a single embedding pass over the full store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

from remi.agent.documents import parse_document
from remi.agent.documents.types import DocumentKind
from remi.application.portfolio.auto_assign import AutoAssignService
from remi.application.services.embedding.pipeline import EmbeddingPipeline
from remi.application.services.ingestion.pipeline import DocumentIngestService
from remi.application.services.ingestion.rules import detect_report_type

logger = structlog.get_logger(__name__)

REPORT_SUFFIXES: frozenset[str] = frozenset(
    {".csv", ".xlsx", ".xls", ".pdf", ".docx", ".txt"}
)


def discover_reports(directory: str | Path) -> list[Path]:
    """Return sorted list of ingestible report files in *directory*."""
    target = Path(directory)
    if not target.is_dir():
        return []
    return sorted(
        f for f in target.iterdir() if f.is_file() and f.suffix.lower() in REPORT_SUFFIXES
    )


def _content_type_for(path: Path) -> str:
    return {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
    }.get(path.suffix.lower(), "application/octet-stream")


def _is_property_directory(path: Path) -> bool:
    """Return True if this file's column headers match a property_directory report.

    Parses the file once to inspect column names. Non-tabular files (PDF, DOCX,
    TXT) return False immediately since they can never be a property directory.
    """
    if path.suffix.lower() in {".pdf", ".docx", ".txt"}:
        return False
    try:
        content_bytes = path.read_bytes()
        content_type = _content_type_for(path)
        parsed = parse_document(path.name, content_bytes, content_type)
        if parsed.kind != DocumentKind.TABULAR:
            return False
        match = detect_report_type(parsed.column_names)
        return match is not None and match[0] == "property_directory"
    except Exception:
        logger.warning(
            "report_type_detection_failed",
            filename=path.name,
            exc_info=True,
        )
        return False


def _partition_files(files: list[Path]) -> tuple[list[Path], list[Path]]:
    """Split files into (property_directory_files, other_files)."""
    prop_dir: list[Path] = []
    others: list[Path] = []
    for f in files:
        if _is_property_directory(f):
            prop_dir.append(f)
        else:
            others.append(f)
    return prop_dir, others


@dataclass
class LoadResult:
    files_processed: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    total_embedded: int = 0
    errors: list[str] = field(default_factory=list)


class PortfolioLoader:
    """Bulk-loads AppFolio report exports into the property store and KB.

    Processes property_directory files first to establish the manager/portfolio
    registry, then ingests all other reports. A single embedding pass runs
    after all files have been processed.
    """

    def __init__(
        self,
        document_ingest: DocumentIngestService,
        embedding_pipeline: EmbeddingPipeline,
        auto_assign: AutoAssignService | None = None,
        metadata_skip_patterns: tuple[str, ...] = (),
    ) -> None:
        self._document_ingest = document_ingest
        self._embedding_pipeline = embedding_pipeline
        self._auto_assign = auto_assign
        self._skip_patterns = metadata_skip_patterns

    async def load_reports(
        self,
        directory: str | Path,
        *,
        manager: str | None = None,
        run_embed: bool = True,
    ) -> LoadResult:
        """Ingest all report files in *directory*, property_directory first.

        Args:
            directory: Path to a directory of AppFolio exports, or a single file.
            manager: Optional manager tag to associate with all ingested data.
            run_embed: Whether to run the embedding pipeline after all files.

        Returns:
            LoadResult summarising files processed, entities created, and any errors.
        """
        result = LoadResult()
        target = Path(directory)

        if not target.exists():
            result.errors.append(f"Directory not found: {directory}")
            return result

        if target.is_dir():
            files = discover_reports(target)
        else:
            files = [target] if target.suffix.lower() in REPORT_SUFFIXES else []

        if not files:
            logger.info("load_reports_no_files", directory=str(directory))
            return result

        prop_dir_files, other_files = _partition_files(files)

        if prop_dir_files:
            logger.info(
                "load_reports_pass1_start",
                count=len(prop_dir_files),
                files=[f.name for f in prop_dir_files],
            )
        else:
            logger.warning(
                "load_reports_no_property_directory",
                directory=str(directory),
                hint="Upload a Property Directory report first for correct manager assignment.",
            )

        for file in [*prop_dir_files, *other_files]:
            await self._ingest_file(file, manager=manager, result=result)

        if self._auto_assign:
            try:
                assign_result = await self._auto_assign.auto_assign()
                logger.info(
                    "load_reports_auto_assign",
                    assigned=assign_result.assigned,
                    unresolved=assign_result.unresolved,
                )
            except Exception:
                logger.warning("load_reports_auto_assign_failed", exc_info=True)
                result.errors.append("auto_assign failed")

        if run_embed:
            try:
                embed_result = await self._embedding_pipeline.run_full()
                result.total_embedded = embed_result.embedded
                logger.info("load_reports_embedding_complete", embedded=embed_result.embedded)
            except Exception:
                logger.warning("load_reports_embedding_failed", exc_info=True)
                result.errors.append("embedding_pipeline failed")

        logger.info(
            "load_reports_complete",
            files=result.files_processed,
            entities=result.total_entities,
            relationships=result.total_relationships,
            embedded=result.total_embedded,
            errors=len(result.errors),
        )
        return result

    async def _ingest_file(
        self,
        file: Path,
        *,
        manager: str | None,
        result: LoadResult,
    ) -> None:
        logger.info("load_file_start", filename=file.name)
        try:
            content_bytes = file.read_bytes()
            content_type = _content_type_for(file)

            ingest_result = await self._document_ingest.ingest_upload(
                file.name,
                content_bytes,
                content_type,
                manager=manager,
                run_pipelines=False,
            )

            result.files_processed += 1
            result.total_entities += ingest_result.entities_extracted
            result.total_relationships += ingest_result.relationships_extracted
            if ingest_result.pipeline_warnings:
                result.errors.extend(ingest_result.pipeline_warnings)

            logger.info(
                "load_file_complete",
                filename=file.name,
                entities=ingest_result.entities_extracted,
                rels=ingest_result.relationships_extracted,
                report_type=ingest_result.report_type,
            )

        except Exception:
            logger.warning("load_file_failed", filename=file.name, exc_info=True)
            result.errors.append(f"Failed: {file.name}")
