"""Usage API — LLM cost and token tracking across all call sites."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Request

from remi.agent.observe.usage import LLMUsageLedger, UsageReport, UsageSummary

router = APIRouter(prefix="/usage", tags=["usage"])


def _get_ledger(request: Request) -> LLMUsageLedger:
    return request.app.state.container.usage_ledger


@router.get("")
async def usage_report(
    request: Request,
    hours: int | None = Query(None, description="Filter to last N hours"),
    recent_limit: int = Query(20, ge=1, le=100, description="Number of recent records"),
) -> UsageReport:
    ledger = _get_ledger(request)
    since = datetime.now(UTC) - timedelta(hours=hours) if hours else None
    return ledger.report(since=since, recent_limit=recent_limit)


@router.get("/summary")
async def usage_summary(
    request: Request,
    hours: int | None = Query(None, description="Filter to last N hours"),
) -> UsageSummary:
    ledger = _get_ledger(request)
    since = datetime.now(UTC) - timedelta(hours=hours) if hours else None
    return ledger.summary(since=since)
