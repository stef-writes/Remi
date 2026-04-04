"""Operations — the work.

Vendor, MaintenanceRequest.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from remi.application.core.models._helpers import _utcnow
from remi.application.core.models.enums import (
    MaintenanceCategory,
    MaintenanceSource,
    MaintenanceStatus,
    Priority,
    VendorCategory,
)


class Vendor(BaseModel, frozen=True):
    """A service provider contracted for maintenance, repairs, or renovations.

    ``is_internal`` distinguishes the firm's own maintenance company from
    outside contractors — critical for performance tracking when the PM
    company is vertically integrated.
    """

    id: str
    name: str
    category: VendorCategory = VendorCategory.GENERAL
    phone: str | None = None
    email: str | None = None
    is_internal: bool = False
    license_number: str | None = None
    insurance_expiry: date | None = None
    rating: float | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class MaintenanceRequest(BaseModel, frozen=True):
    id: str
    unit_id: str
    property_id: str
    tenant_id: str | None = None
    category: MaintenanceCategory = MaintenanceCategory.GENERAL
    priority: Priority = Priority.MEDIUM
    source: MaintenanceSource | None = None
    title: str = ""
    description: str = ""
    status: MaintenanceStatus = MaintenanceStatus.OPEN
    vendor_id: str | None = None
    vendor: str | None = None  # COMPAT: freeform vendor name, prefer vendor_id
    scheduled_date: date | None = None
    completed_date: date | None = None
    sla_hours: int | None = None
    invoice_amount: Decimal | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    resolved_at: datetime | None = None
    cost: Decimal | None = None
