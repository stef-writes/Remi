"""Seed endpoint — ingest sample AppFolio reports in correct dependency order.

POST /api/v1/seed/reports   — ingest the bundled sample reports
POST /api/v1/seed/demo      — load synthetic demo data (Alice Chen / Bob Diaz)
DELETE /api/v1/seed         — clear all in-memory state (restart-equivalent)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from remi.api.dependencies import get_auto_assign_service, get_container, get_document_ingest
from remi.config.container import Container
from remi.services.auto_assign import AutoAssignService
from remi.services.document_ingest import DocumentIngestService

router = APIRouter(prefix="/seed", tags=["seed"])
logger = structlog.get_logger("remi.seed")

# Relative to the project root (two levels above the package src/remi dir).
_PACKAGE_ROOT = Path(__file__).resolve().parents[4]
_SAMPLE_DIR = _PACKAGE_ROOT / "data" / "sample_reports" / "Alex_Budavich_Reports"

# Ingest order matters: property directory creates the manager/property spine
# that delinquency and lease expiration attach to. Rent roll last since it's
# vacancy-only and has no manager tags.
_REPORT_ORDER = [
    "property_directory-20260330.xlsx",
    "Delinquency.xlsx",
    "Lease Expiration Detail By Month.xlsx",
    "Rent Roll_Vacancy (1).xlsx",
]


class SeedResult(BaseModel):
    ok: bool
    reports_ingested: list[dict[str, Any]]
    managers_created: int
    properties_created: int
    auto_assigned: int
    signals_produced: int
    errors: list[str]


class DemoSeedResult(BaseModel):
    ok: bool
    summary: str


@router.post("/reports", response_model=SeedResult)
async def seed_reports(
    ingest: DocumentIngestService = Depends(get_document_ingest),
    auto_assign: AutoAssignService = Depends(get_auto_assign_service),
    container: Container = Depends(get_container),
) -> SeedResult:
    """Ingest the bundled AppFolio sample reports in dependency order.

    Safe to call multiple times — documents and entities are upserted, not
    duplicated. Triggers auto-assign and signal pipeline after ingestion.
    """
    if not _SAMPLE_DIR.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Sample reports directory not found: {_SAMPLE_DIR}",
        )

    reports_ingested: list[dict[str, Any]] = []
    errors: list[str] = []
    total_entities = 0

    for filename in _REPORT_ORDER:
        path = _SAMPLE_DIR / filename
        if not path.exists():
            errors.append(f"Missing: {filename}")
            logger.warning("seed_report_missing", filename=filename, path=str(path))
            continue

        try:
            content = path.read_bytes()
            result = await ingest.ingest_upload(filename, content, "", manager=None)
            reports_ingested.append(
                {
                    "filename": filename,
                    "report_type": result.report_type,
                    "rows": result.doc.row_count,
                    "entities": result.entities_extracted,
                    "relationships": result.relationships_extracted,
                }
            )
            total_entities += result.entities_extracted
            logger.info(
                "seed_report_ingested",
                filename=filename,
                report_type=result.report_type,
                rows=result.doc.row_count,
                entities=result.entities_extracted,
            )
        except Exception as exc:
            msg = f"{filename}: {exc}"
            errors.append(msg)
            logger.exception("seed_report_failed", filename=filename)

    # Auto-assign: wire properties to managers from embedded tags
    assigned = 0
    try:
        assign_result = await auto_assign.auto_assign()
        assigned = assign_result.assigned
        logger.info("seed_auto_assign_complete", assigned=assigned)
    except Exception:
        logger.exception("seed_auto_assign_failed")

    # Run signal pipeline so the dashboard lights up
    signals_produced = 0
    try:
        sig_result = await container.signal_pipeline.run_all()
        signals_produced = sig_result.produced
        logger.info("seed_signals_complete", produced=signals_produced)
    except Exception:
        logger.exception("seed_signals_failed")

    # Count managers and properties now in the store
    managers = await container.property_store.list_managers()
    properties = await container.property_store.list_properties()

    return SeedResult(
        ok=len(errors) == 0,
        reports_ingested=reports_ingested,
        managers_created=len(managers),
        properties_created=len(properties),
        auto_assigned=assigned,
        signals_produced=signals_produced,
        errors=errors,
    )


@router.post("/demo", response_model=DemoSeedResult)
async def seed_demo(
    container: Container = Depends(get_container),
) -> DemoSeedResult:
    """Load synthetic demo data (Alice Chen / Bob Diaz — Portland)."""
    from remi.cli.seed import seed_into

    try:
        summary = await seed_into(container.property_store)
        await container.signal_pipeline.run_all()
        await container.embedding_pipeline.run_full()
        return DemoSeedResult(ok=True, summary=summary)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
