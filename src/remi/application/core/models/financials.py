"""Financials — temporal balance observations.

BalanceObservation records what a delinquency report said at a point in time.
Multiple observations accumulate; the latest is current state, the history
gives trend data that the AI can reason over.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from remi.application.core.models._helpers import _utcnow


class BalanceObservation(BaseModel, frozen=True):
    """A balance snapshot recorded from a single delinquency report run.

    Each report ingestion creates a new observation; records are never
    overwritten so the full history is preserved.
    """

    id: str
    tenant_id: str
    lease_id: str | None = None
    property_id: str
    observed_at: datetime
    balance_total: Decimal = Decimal("0")
    balance_0_30: Decimal = Decimal("0")
    balance_30_plus: Decimal = Decimal("0")
    subsidy_balance: Decimal = Decimal("0")
    last_payment_date: date | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
