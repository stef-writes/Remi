"""Usage API — LLM cost and token tracking across all call sites."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from remi.agent.observe import UsageReport, UsageSummary
from remi.shell.api.dependencies import Ctr

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def usage_report(
    c: Ctr,
    hours: int | None = Query(None, description="Filter to last N hours"),
    recent_limit: int = Query(20, ge=1, le=100, description="Number of recent records"),
) -> UsageReport:
    since = datetime.now(UTC) - timedelta(hours=hours) if hours else None
    return c.usage_ledger.report(since=since, recent_limit=recent_limit)


@router.get("/summary")
async def usage_summary(
    c: Ctr,
    hours: int | None = Query(None, description="Filter to last N hours"),
) -> UsageSummary:
    since = datetime.now(UTC) - timedelta(hours=hours) if hours else None
    return c.usage_ledger.summary(since=since)
