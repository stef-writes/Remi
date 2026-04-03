"""Centralized LLM usage ledger — records every LLM call across the system.

Every call site (agent runtime streaming, ingestion pipeline, future
embedding calls) appends an immutable UsageRecord. The ledger provides
aggregation views by source, model, provider, and time window.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from enum import StrEnum, unique

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


@unique
class UsageSource(StrEnum):
    """Where the LLM call originated."""

    AGENT = "agent"
    INGESTION = "ingestion"


class UsageRecord(BaseModel, frozen=True):
    """A single LLM call's token usage and estimated cost."""

    timestamp: datetime = Field(default_factory=_utcnow)
    source: UsageSource
    source_detail: str = ""
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    estimated_cost_usd: float | None = None
    trace_id: str | None = None


class UsageSummary(BaseModel, frozen=True):
    """Aggregated usage across multiple records."""

    total_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_estimated_cost_usd: float = 0.0


class UsageBreakdown(BaseModel, frozen=True):
    """Usage grouped by a dimension (source, model, provider)."""

    key: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class UsageReport(BaseModel, frozen=True):
    """Full usage report returned by the API."""

    summary: UsageSummary
    by_source: list[UsageBreakdown] = Field(default_factory=list)
    by_model: list[UsageBreakdown] = Field(default_factory=list)
    by_provider: list[UsageBreakdown] = Field(default_factory=list)
    recent: list[UsageRecord] = Field(default_factory=list)


class LLMUsageLedger:
    """Thread-safe, in-memory ledger of all LLM usage.

    Append-only. The ledger is queried for aggregated views and
    recent call history. Records are never mutated after creation.
    """

    def __init__(self, max_records: int = 10_000) -> None:
        self._records: list[UsageRecord] = []
        self._max_records = max_records
        self._lock = threading.Lock()

    def record(self, entry: UsageRecord) -> None:
        with self._lock:
            self._records.append(entry)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

    @property
    def records(self) -> list[UsageRecord]:
        with self._lock:
            return list(self._records)

    def summary(self, *, since: datetime | None = None) -> UsageSummary:
        recs = self._filtered(since)
        return UsageSummary(
            total_calls=len(recs),
            total_prompt_tokens=sum(r.prompt_tokens for r in recs),
            total_completion_tokens=sum(r.completion_tokens for r in recs),
            total_tokens=sum(r.total_tokens for r in recs),
            total_cache_read_tokens=sum(r.cache_read_tokens for r in recs),
            total_estimated_cost_usd=sum(r.estimated_cost_usd or 0.0 for r in recs),
        )

    def report(self, *, since: datetime | None = None, recent_limit: int = 20) -> UsageReport:
        recs = self._filtered(since)
        return UsageReport(
            summary=self.summary(since=since),
            by_source=self._group_by(recs, lambda r: r.source.value),
            by_model=self._group_by(recs, lambda r: r.model),
            by_provider=self._group_by(recs, lambda r: r.provider),
            recent=list(reversed(recs[-recent_limit:])),
        )

    def _filtered(self, since: datetime | None) -> list[UsageRecord]:
        if since is None:
            return self.records
        return [r for r in self.records if r.timestamp >= since]

    @staticmethod
    def _group_by(
        recs: list[UsageRecord],
        key_fn: object,
    ) -> list[UsageBreakdown]:
        from collections import defaultdict

        groups: dict[str, list[UsageRecord]] = defaultdict(list)
        for r in recs:
            groups[key_fn(r)].append(r)  # type: ignore[operator]

        result = []
        for key, group in sorted(groups.items()):
            result.append(
                UsageBreakdown(
                    key=key,
                    calls=len(group),
                    prompt_tokens=sum(r.prompt_tokens for r in group),
                    completion_tokens=sum(r.completion_tokens for r in group),
                    total_tokens=sum(r.total_tokens for r in group),
                    estimated_cost_usd=sum(r.estimated_cost_usd or 0.0 for r in group),
                )
            )
        return result
