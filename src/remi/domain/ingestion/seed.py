"""SeedService — ingest AppFolio report exports in dependency order.

Encapsulates the full seed workflow: parse XLSX reports, auto-assign
properties to managers via embedded tags, run signal + embedding pipelines.
Used by both the CLI (``remi seed``) and the API (``POST /api/v1/seed/reports``).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from pydantic import BaseModel

from remi.agent.signals.composite import CompositeProducer
from remi.domain.ingestion.embedding import EmbeddingPipeline
from remi.domain.ingestion.pipeline import DocumentIngestService
from remi.domain.portfolio.protocols import PropertyStore
from remi.domain.queries.auto_assign import AutoAssignService
from remi.domain.queries.rollups import ManagerSnapshot, RollupStore
from remi.domain.queries.snapshots import SnapshotService

logger = structlog.get_logger(__name__)

DEFAULT_SAMPLE_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "sample_reports" / "Alex_Budavich_Reports"
)

REPORT_ORDER = [
    "property_directory-20260330.xlsx",
    "Delinquency.xlsx",
    "Lease Expiration Detail By Month.xlsx",
    "Rent Roll_Vacancy (1).xlsx",
]

BACKFILL_WEEKS = 12


class IngestedReport(BaseModel, frozen=True):
    filename: str
    report_type: str
    rows: int
    entities: int
    relationships: int


@dataclass
class SeedResult:
    ok: bool = True
    reports_ingested: list[IngestedReport] = field(default_factory=list)
    managers_created: int = 0
    properties_created: int = 0
    auto_assigned: int = 0
    signals_produced: int = 0
    history_snapshots: int = 0
    errors: list[str] = field(default_factory=list)


class SeedService:
    """Orchestrates seeding from a directory of AppFolio XLSX exports."""

    def __init__(
        self,
        document_ingest: DocumentIngestService,
        auto_assign: AutoAssignService,
        signal_pipeline: CompositeProducer,
        embedding_pipeline: EmbeddingPipeline,
        property_store: PropertyStore,
        snapshot_service: SnapshotService | None = None,
        rollup_store: RollupStore | None = None,
    ) -> None:
        self._ingest = document_ingest
        self._auto_assign = auto_assign
        self._signal_pipeline = signal_pipeline
        self._embedding_pipeline = embedding_pipeline
        self._ps = property_store
        self._snapshot = snapshot_service
        self._rollup = rollup_store

    async def seed_from_reports(
        self,
        report_dir: Path | None = None,
    ) -> SeedResult:
        """Ingest reports in dependency order, auto-assign, run pipelines.

        Reports are ingested cheaply first (parse + KB/store writes only),
        then the expensive pipelines (signals, embeddings) run once at the
        end instead of per-report.
        """
        report_dir = report_dir or DEFAULT_SAMPLE_DIR
        result = SeedResult()

        if not report_dir.exists():
            result.ok = False
            result.errors.append(f"Report directory not found: {report_dir}")
            return result

        # --- Phase 1: Ingest all reports (cheap — no signals/embed) ----------
        for filename in REPORT_ORDER:
            path = report_dir / filename
            if not path.exists():
                result.errors.append(f"Missing: {filename}")
                logger.warning("seed_report_missing", filename=filename, path=str(path))
                continue

            try:
                content = path.read_bytes()
                ingest_result = await self._ingest.ingest_upload(
                    filename,
                    content,
                    "",
                    manager=None,
                    run_pipelines=False,
                )
                result.reports_ingested.append(
                    IngestedReport(
                        filename=filename,
                        report_type=ingest_result.report_type,
                        rows=ingest_result.doc.row_count,
                        entities=ingest_result.entities_extracted,
                        relationships=ingest_result.relationships_extracted,
                    )
                )
                logger.info(
                    "seed_report_ingested",
                    filename=filename,
                    report_type=ingest_result.report_type,
                    rows=ingest_result.doc.row_count,
                    entities=ingest_result.entities_extracted,
                )
            except Exception as exc:
                msg = f"{filename}: {exc}"
                result.errors.append(msg)
                logger.exception("seed_report_failed", filename=filename)

        # --- Phase 2: Auto-assign, then expensive pipelines once -------------
        try:
            assign_result = await self._auto_assign.auto_assign()
            result.auto_assigned = assign_result.assigned
            logger.info("seed_auto_assign_complete", assigned=assign_result.assigned)
        except Exception as exc:
            result.errors.append(f"auto_assign: {exc}")
            logger.exception("seed_auto_assign_failed")

        try:
            sig_result = await self._signal_pipeline.run_all()
            result.signals_produced = sig_result.produced
            logger.info("seed_signals_complete", produced=sig_result.produced)
        except Exception as exc:
            result.errors.append(f"signal_pipeline: {exc}")
            logger.exception("seed_signals_failed")

        try:
            embed_result = await self._embedding_pipeline.run_full()
            logger.info("seed_embeddings_complete", embedded=embed_result.embedded)
        except Exception as exc:
            result.errors.append(f"embedding_pipeline: {exc}")
            logger.exception("seed_embeddings_failed")

        managers = await self._ps.list_managers()
        properties = await self._ps.list_properties()
        result.managers_created = len(managers)
        result.properties_created = len(properties)

        # --- Phase 3: Backfill historical snapshots --------------------------
        try:
            result.history_snapshots = await self._backfill_history()
            logger.info(
                "seed_history_backfill_complete",
                snapshots=result.history_snapshots,
            )
        except Exception as exc:
            result.errors.append(f"history_backfill: {exc}")
            logger.exception("seed_history_backfill_failed")

        result.ok = len(result.errors) == 0
        return result

    async def _backfill_history(self) -> int:
        """Generate weekly historical snapshots with realistic variance.

        Takes a real snapshot of current state and projects it backwards
        in time with small gaussian perturbations, giving the researcher
        agent actual temporal depth to analyze trends.
        """
        if self._snapshot is None or self._rollup is None:
            return 0

        baseline = await self._snapshot.capture()
        if not baseline:
            return 0

        rng = random.Random(42)
        now = datetime.now(UTC)
        count = 0

        for week in range(BACKFILL_WEEKS, 0, -1):
            ts = now - timedelta(weeks=week)
            mgr_batch: list[ManagerSnapshot] = []
            for snap in baseline:
                mgr_batch.append(_perturb_manager(snap, ts, week, rng))
            await self._rollup.append_manager_snapshots(mgr_batch)
            count += len(mgr_batch)

        logger.info(
            "seed_history_backfill",
            weeks=BACKFILL_WEEKS,
            managers=len(baseline),
            total_snapshots=count,
        )
        return count


def _perturb_manager(
    snap: ManagerSnapshot,
    ts: datetime,
    weeks_ago: int,
    rng: random.Random,
) -> ManagerSnapshot:
    """Create a historical variant of a manager snapshot.

    Metrics drift proportionally to how far back in time we go:
    older snapshots are slightly worse (higher delinquency, lower
    occupancy) to simulate gradual improvement over 12 weeks.
    """
    drift = weeks_ago / BACKFILL_WEEKS

    def noise() -> float:
        return 1.0 + rng.gauss(0, 0.02)

    occ = max(0, snap.occupied - int(drift * snap.total_units * 0.03 * noise()))
    vac = snap.total_units - occ
    occ_rate = round(occ / snap.total_units, 3) if snap.total_units else 0.0

    del_count = max(0, int(snap.delinquent_count * (1.0 + drift * 0.15) * noise()))
    del_bal = max(0.0, snap.delinquent_balance * (1.0 + drift * 0.12) * noise())

    rent = max(0.0, snap.total_rent * (1.0 - drift * 0.02) * noise())
    market = max(0.0, snap.total_market_rent * noise())
    ltl = max(0.0, snap.loss_to_lease * (1.0 + drift * 0.08) * noise())

    return ManagerSnapshot(
        manager_id=snap.manager_id,
        manager_name=snap.manager_name,
        timestamp=ts,
        property_count=snap.property_count,
        total_units=snap.total_units,
        occupied=occ,
        vacant=vac,
        occupancy_rate=occ_rate,
        total_rent=round(rent, 2),
        total_market_rent=round(market, 2),
        loss_to_lease=round(ltl, 2),
        delinquent_count=del_count,
        delinquent_balance=round(del_bal, 2),
    )
