"""Leasing — who's in them, on what terms.

Tenant, Lease.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from remi.application.core.models._helpers import _utcnow
from remi.application.core.models.enums import (
    LeaseStatus,
    LeaseType,
    RenewalStatus,
    TenantStatus,
)


class Tenant(BaseModel, frozen=True):
    id: str
    name: str
    email: str = ""
    phone: str | None = None
    status: TenantStatus = TenantStatus.CURRENT
    balance_owed: Decimal = Decimal("0")
    balance_0_30: Decimal = Decimal("0")
    balance_30_plus: Decimal = Decimal("0")
    balance_31_60: Decimal = Decimal("0")
    balance_61_90: Decimal = Decimal("0")
    balance_90_plus: Decimal = Decimal("0")
    last_payment_date: date | None = None
    subsidy_program: str | None = None
    subsidy_amount: Decimal | None = None
    move_in_date: date | None = None
    move_out_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    lease_ids: list[str] = Field(default_factory=list)
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Lease(BaseModel, frozen=True):
    id: str
    unit_id: str
    tenant_id: str
    property_id: str
    start_date: date
    end_date: date
    monthly_rent: Decimal
    deposit: Decimal = Decimal("0")
    status: LeaseStatus = LeaseStatus.ACTIVE
    market_rent: Decimal = Decimal("0")
    is_month_to_month: bool = False
    lease_type: LeaseType | None = None
    notice_days: int | None = None
    renewal_status: RenewalStatus | None = None
    renewal_offered_date: date | None = None
    renewal_offer_rent: Decimal | None = None
    renewal_offer_term_months: int | None = None
    concession_amount: Decimal | None = None
    concession_months: int | None = None
    prior_lease_id: str | None = None
    subsidy_program: str | None = None
    notice_date: date | None = None
    move_in_date: date | None = None
    move_out_date: date | None = None
    source_document_id: str | None = None
