"""SeedService — ingest AppFolio report exports in dependency order.

Encapsulates the full seed workflow: parse XLSX reports, auto-assign
properties to managers via embedded tags, run signal + embedding pipelines.
Used by both the CLI (``remi seed``) and the API (``POST /api/v1/seed/reports``).

Accepts any directory of XLSX/CSV exports — report type is detected by
the LLM ingestion pipeline from column headers and row content, not from
filenames.  Property directory reports (the "migration" type that creates
managers and properties) are detected by a lightweight column-header
heuristic and ingested first so that dependent reports can attach to
existing entities.

On first run the full LLM pipeline executes and all in-memory store state
is snapshot to a cache file next to the reports.  Subsequent runs hydrate
from cache in ~200ms, skipping LLM entirely.  Cache auto-invalidates when
source report files change.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from pydantic import BaseModel

from remi.agent.documents.parsers import parse_document
from remi.agent.signals.producers.composite import CompositeProducer
from remi.application.core.protocols import PropertyStore
from remi.application.services.ingestion.pipeline import DocumentIngestService
from remi.application.services.embedding.pipeline import EmbeddingPipeline
from remi.application.services.seeding.cache import (
    StoreBundle,
    cache_path_for,
    is_stale,
)
from remi.application.services.seeding.cache import load as cache_load
from remi.application.services.seeding.cache import save as cache_save
from remi.application.services.queries.auto_assign import AutoAssignService
from remi.application.core.rollups import ManagerSnapshot, RollupStore
from remi.application.services.monitoring.snapshots.service import SnapshotService

logger = structlog.get_logger(__name__)

_REPORT_EXTENSIONS = frozenset({".xlsx", ".xls", ".csv"})

_PROPERTY_DIR_COLUMNS = frozenset({
    "site manager name",
    "property manager",
    "manager name",
    "assigned manager",
})

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


def _is_property_directory(
    path: Path,
    extra_skip_patterns: tuple[str, ...] = (),
) -> bool:
    """Heuristic: parse just the column headers and check for manager columns."""
    try:
        doc = parse_document(
            path.name, path.read_bytes(), "",
            extra_skip_patterns=extra_skip_patterns,
        )
        lower_cols = {c.lower().strip() for c in doc.column_names}
        return bool(lower_cols & _PROPERTY_DIR_COLUMNS)
    except Exception:
        return False


def discover_reports(
    report_dir: Path,
    extra_skip_patterns: tuple[str, ...] = (),
) -> list[Path]:
    """Find report files and order them: property directories first.

    Uses a lightweight column-header heuristic to detect property directory
    reports so they are ingested before dependent report types.
    """
    all_files = sorted(
        p for p in report_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _REPORT_EXTENSIONS
    )
    if not all_files:
        return []

    prop_dirs: list[Path] = []
    others: list[Path] = []
    for p in all_files:
        if _is_property_directory(p, extra_skip_patterns):
            prop_dirs.append(p)
        else:
            others.append(p)

    return prop_dirs + others


class SeedService:
    """Orchestrates seeding from a directory of AppFolio exports."""

    def __init__(
        self,
        document_ingest: DocumentIngestService,
        auto_assign: AutoAssignService,
        signal_pipeline: CompositeProducer,
        embedding_pipeline: EmbeddingPipeline,
        property_store: PropertyStore,
        snapshot_service: SnapshotService | None = None,
        rollup_store: RollupStore | None = None,
        store_bundle: StoreBundle | None = None,
        metadata_skip_patterns: tuple[str, ...] = (),
    ) -> None:
        self._ingest = document_ingest
        self._auto_assign = auto_assign
        self._signal_pipeline = signal_pipeline
        self._embedding_pipeline = embedding_pipeline
        self._ps = property_store
        self._snapshot = snapshot_service
        self._rollup = rollup_store
        self._store_bundle = store_bundle
        self._skip_patterns = metadata_skip_patterns

    async def seed_from_reports(
        self,
        report_dir: Path | None = None,
        *,
        force: bool = False,
    ) -> SeedResult:
        """Ingest reports in dependency order, auto-assign, run pipelines.

        Accepts any directory of XLSX/CSV exports.  Report type is detected
        by the LLM pipeline — filenames don't matter.  Property directory
        reports are discovered via column-header heuristic and ingested first.

        On first run the full LLM pipeline runs and state is cached.
        Subsequent runs hydrate from cache unless *force* is True or source
        files have changed.
        """
        if report_dir is None:
            raise ValueError(
                "report_dir is required — pass the directory containing your "
                "AppFolio XLSX/CSV exports."
            )
        result = SeedResult()

        if not report_dir.exists():
            result.ok = False
            result.errors.append(f"Report directory not found: {report_dir}")
            return result

        # --- Cache fast path --------------------------------------------------
        if (
            self._store_bundle is not None
            and not force
            and not is_stale(cache_path_for(report_dir), report_dir)
            and cache_load(self._store_bundle, cache_path_for(report_dir))
        ):
            managers = await self._ps.list_managers()
            properties = await self._ps.list_properties()
            result.managers_created = len(managers)
            result.properties_created = len(properties)
            logger.info(
                "seed_from_cache",
                managers=result.managers_created,
                properties=result.properties_created,
            )
            return result

        # --- Full pipeline path -----------------------------------------------
        ordered = discover_reports(report_dir, self._skip_patterns)
        if not ordered:
            result.ok = False
            result.errors.append(
                f"No report files ({', '.join(_REPORT_EXTENSIONS)}) "
                f"found in {report_dir}"
            )
            return result

        logger.info(
            "seed_reports_discovered",
            count=len(ordered),
            files=[p.name for p in ordered],
        )

        # Phase 1: Ingest all reports (cheap — no signals/embed)
        for path in ordered:
            try:
                content = path.read_bytes()
                ingest_result = await self._ingest.ingest_upload(
                    path.name,
                    content,
                    "",
                    manager=None,
                    run_pipelines=False,
                )
                result.reports_ingested.append(
                    IngestedReport(
                        filename=path.name,
                        report_type=ingest_result.report_type,
                        rows=ingest_result.doc.row_count,
                        entities=ingest_result.entities_extracted,
                        relationships=ingest_result.relationships_extracted,
                    )
                )
                logger.info(
                    "seed_report_ingested",
                    filename=path.name,
                    report_type=ingest_result.report_type,
                    rows=ingest_result.doc.row_count,
                    entities=ingest_result.entities_extracted,
                )
            except Exception as exc:
                msg = f"{path.name}: {exc}"
                result.errors.append(msg)
                logger.exception("seed_report_failed", filename=path.name)

        # Phase 2: Auto-assign, then expensive pipelines once
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

        # Phase 3: Backfill historical snapshots
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

        # --- Save cache after successful full pipeline run --------------------
        if self._store_bundle is not None and result.ok:
            try:
                cache_save(self._store_bundle, cache_path_for(report_dir))
            except Exception:
                logger.warning("seed_cache_save_failed", exc_info=True)

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
