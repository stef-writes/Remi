"""Usage API — LLM cost and token tracking across all call sites."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query, Request

from remi.agent.observe.usage import LLMUsageLedger

router = APIRouter(prefix="/usage", tags=["usage"])


def _get_ledger(request: Request) -> LLMUsageLedger:
    return request.app.state.container.usage_ledger


@router.get("")
async def usage_report(
    request: Request,
    hours: int | None = Query(None, description="Filter to last N hours"),
    recent_limit: int = Query(20, ge=1, le=100, description="Number of recent records"),
) -> dict[str, Any]:
    """Full usage report with breakdowns by source, model, and provider."""
    ledger = _get_ledger(request)
    since = datetime.now(UTC) - timedelta(hours=hours) if hours else None
    report = ledger.report(since=since, recent_limit=recent_limit)
    return report.model_dump()


@router.get("/summary")
async def usage_summary(
    request: Request,
    hours: int | None = Query(None, description="Filter to last N hours"),
) -> dict[str, Any]:
    """Lightweight summary — total calls, tokens, estimated cost."""
    ledger = _get_ledger(request)
    since = datetime.now(UTC) - timedelta(hours=hours) if hours else None
    return ledger.summary(since=since).model_dump()
