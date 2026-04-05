"""Report load endpoints — bulk-ingest AppFolio exports from a directory.

POST /api/v1/reports/load — process all reports in a directory
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from remi.application.services.seeding import LoadResult
from remi.shell.api.dependencies import Ctr
from remi.types.errors import IngestionError

router = APIRouter(prefix="/reports", tags=["reports"])
logger = structlog.get_logger("remi.reports")


class LoadRequest(BaseModel):
    report_dir: str
    manager: str | None = None


class LoadResponse(BaseModel):
    ok: bool
    files_processed: int
    total_entities: int
    total_relationships: int
    total_embedded: int
    errors: list[str]


def _to_response(result: LoadResult) -> LoadResponse:
    return LoadResponse(
        ok=len(result.errors) == 0,
        files_processed=result.files_processed,
        total_entities=result.total_entities,
        total_relationships=result.total_relationships,
        total_embedded=result.total_embedded,
        errors=result.errors,
    )


@router.post("/load", response_model=LoadResponse)
async def load_reports(
    body: LoadRequest,
    c: Ctr,
) -> LoadResponse:
    """Load AppFolio exports from a directory.

    Report type is detected from column headers — filenames don't matter.
    Property Directory files are always processed first so that manager and
    portfolio associations resolve correctly for all subsequent reports.
    Safe to call multiple times; existing data is merged idempotently.
    """
    result = await c.portfolio_loader.load_reports(
        Path(body.report_dir),
        manager=body.manager,
    )
    if result.errors and result.files_processed == 0:
        raise IngestionError(result.errors[0] if result.errors else "Report load failed")
    return _to_response(result)
