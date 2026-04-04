"""Seed endpoints — ingest AppFolio report exports.

POST /api/v1/seed/reports          — ingest from an explicit directory
POST /api/v1/seed/reports/bundled  — ingest the bundled sample reports
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from remi.application.services.seeding.service import IngestedReport, SeedService
from remi.application.api.dependencies import get_seed_service
from remi.types.errors import IngestionError

router = APIRouter(prefix="/seed", tags=["seed"])
logger = structlog.get_logger("remi.seed")


class SeedRequest(BaseModel):
    report_dir: str


class SeedResponse(BaseModel):
    ok: bool
    reports_ingested: list[IngestedReport]
    managers_created: int
    properties_created: int
    auto_assigned: int
    signals_produced: int
    history_snapshots: int
    errors: list[str]


def _to_response(result: object) -> SeedResponse:
    return SeedResponse(
        ok=result.ok,  # type: ignore[attr-defined]
        reports_ingested=result.reports_ingested,  # type: ignore[attr-defined]
        managers_created=result.managers_created,  # type: ignore[attr-defined]
        properties_created=result.properties_created,  # type: ignore[attr-defined]
        auto_assigned=result.auto_assigned,  # type: ignore[attr-defined]
        signals_produced=result.signals_produced,  # type: ignore[attr-defined]
        history_snapshots=result.history_snapshots,  # type: ignore[attr-defined]
        errors=result.errors,  # type: ignore[attr-defined]
    )


@router.post("/reports", response_model=SeedResponse)
async def seed_reports(
    body: SeedRequest,
    seed_service: SeedService = Depends(get_seed_service),
) -> SeedResponse:
    """Ingest AppFolio exports from a directory.

    Report type is detected by the LLM pipeline — filenames don't matter.
    Property directory reports are ingested first. Safe to call multiple times.
    """
    result = await seed_service.seed_from_reports(Path(body.report_dir))
    if not result.ok and not result.reports_ingested:
        raise IngestionError(result.errors[0] if result.errors else "Seed failed")
    return _to_response(result)


@router.post("/reports/bundled", response_model=SeedResponse)
async def seed_bundled_reports(
    seed_service: SeedService = Depends(get_seed_service),
) -> SeedResponse:
    """Ingest the bundled AppFolio sample reports in dependency order.

    Safe to call multiple times — documents and entities are upserted, not duplicated.
    Triggers auto-assign and signal pipeline after ingestion.
    """
    result = await seed_service.seed_from_reports()
    if not result.ok and not result.reports_ingested:
        raise IngestionError(result.errors[0] if result.errors else "Seed failed")
    return _to_response(result)
