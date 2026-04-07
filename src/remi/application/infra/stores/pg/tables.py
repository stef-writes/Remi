"""SQLModel table definitions for the RE domain.

These are mutable DB-row objects — the store layer converts to/from the
frozen Pydantic read models that the rest of the app uses.

Naming convention: ``<Entity>Row`` to distinguish from the Pydantic DTOs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

_TZDateTime = sa.DateTime(timezone=True)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PropertyManagerRow(SQLModel, table=True):
    __tablename__ = "property_managers"

    id: str = Field(primary_key=True)
    name: str
    email: str = ""
    company: str | None = None
    phone: str | None = None
    manager_tag: str | None = None
    title: str | None = None
    territory: str | None = None
    max_units: int | None = None
    license_number: str | None = None
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class PropertyRow(SQLModel, table=True):
    __tablename__ = "properties"

    id: str = Field(primary_key=True)
    manager_id: str | None = Field(default=None, index=True)
    name: str
    property_type: str = "multi_family"
    asset_class: str | None = None
    year_built: int | None = None
    owner_id: str | None = Field(default=None, index=True)
    unit_count: int | None = None
    neighborhood: str | None = None
    year_renovated: int | None = None
    acquisition_date: date | None = None
    management_start_date: date | None = None
    address_street: str = ""
    address_city: str = ""
    address_state: str = ""
    address_zip_code: str = ""
    address_country: str = "US"
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class UnitRow(SQLModel, table=True):
    __tablename__ = "units"

    id: str = Field(primary_key=True)
    property_id: str = Field(index=True)
    unit_number: str
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    unit_type: str | None = None
    floor: int | None = None
    market_rent: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class LeaseRow(SQLModel, table=True):
    __tablename__ = "leases"

    id: str = Field(primary_key=True)
    unit_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    property_id: str = Field(index=True)
    start_date: date
    end_date: date
    monthly_rent: Decimal = Field(sa_type=sa.Numeric(12, 2))
    deposit: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    status: str = "active"
    market_rent: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    is_month_to_month: bool = False
    notice_date: date | None = None
    move_in_date: date | None = None
    move_out_date: date | None = None
    first_seen_at: datetime | None = Field(default=None, sa_type=_TZDateTime)
    last_confirmed_at: datetime | None = Field(default=None, sa_type=_TZDateTime)
    content_hash: str | None = None
    source_document_id: str | None = None


class TenantRow(SQLModel, table=True):
    __tablename__ = "tenants"

    id: str = Field(primary_key=True)
    name: str
    email: str = ""
    phone: str | None = None
    status: str = "current"
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class BalanceObservationRow(SQLModel, table=True):
    __tablename__ = "balance_observations"

    id: str = Field(primary_key=True)
    tenant_id: str = Field(index=True)
    lease_id: str | None = Field(default=None, index=True)
    property_id: str = Field(index=True)
    observed_at: datetime = Field(sa_type=_TZDateTime)
    balance_total: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    balance_0_30: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    balance_30_plus: Decimal = Field(default=Decimal("0"), sa_type=sa.Numeric(12, 2))
    last_payment_date: date | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class MaintenanceRequestRow(SQLModel, table=True):
    __tablename__ = "maintenance_requests"

    id: str = Field(primary_key=True)
    unit_id: str = Field(index=True)
    property_id: str = Field(index=True)
    tenant_id: str | None = None
    category: str = "general"
    priority: str = "medium"
    source: str | None = None  # who/what initiated (tenant, inspection, etc.)
    title: str = ""
    description: str = ""
    status: str = "open"
    scheduled_date: date | None = None  # when the work is planned
    completed_date: date | None = None  # when the work was actually done (from report)
    resolved_at: datetime | None = Field(default=None, sa_type=_TZDateTime)  # system timestamp
    sla_hours: int | None = None
    cost: Decimal | None = Field(default=None, sa_type=sa.Numeric(12, 2))
    vendor: str | None = None
    vendor_id: str | None = Field(default=None, index=True)
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class ActionItemRow(SQLModel, table=True):
    __tablename__ = "action_items"

    id: str = Field(primary_key=True)
    title: str
    description: str = ""
    status: str = "open"
    priority: str = "medium"
    manager_id: str | None = Field(default=None, index=True)
    property_id: str | None = Field(default=None, index=True)
    tenant_id: str | None = Field(default=None, index=True)
    due_date: date | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class NoteRow(SQLModel, table=True):
    __tablename__ = "notes"

    id: str = Field(primary_key=True)
    content: str
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    provenance: str = "user_stated"
    source_doc: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class OwnerRow(SQLModel, table=True):
    __tablename__ = "owners"

    id: str = Field(primary_key=True)
    name: str
    owner_type: str = "other"
    company: str | None = None
    email: str = ""
    phone: str | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip_code: str | None = None
    address_country: str | None = None
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class VendorRow(SQLModel, table=True):
    __tablename__ = "vendors"

    id: str = Field(primary_key=True)
    name: str
    category: str = "general"
    phone: str | None = None
    email: str | None = None
    is_internal: bool = False
    license_number: str | None = None
    insurance_expiry: date | None = None
    rating: float | None = None
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class AppDocumentRow(SQLModel, table=True):
    """Application-layer Document catalog — provenance for every ingested report.

    Distinct from agent.db.tables.DocumentRow which stores raw content (rows,
    chunks). This table records WHAT was imported, WHEN, and WHAT IT COVERS so
    the agent can reason about data completeness and freshness.
    """

    __tablename__ = "app_documents"

    id: str = Field(primary_key=True)
    filename: str
    content_type: str = ""
    content_hash: str = ""
    document_type: str = "other"
    kind: str = "text"
    page_count: int = 0
    chunk_count: int = 0
    row_count: int = 0
    size_bytes: int = 0
    tags: list[str] = Field(default_factory=list, sa_type=sa.JSON)

    # Report provenance
    report_type: str = "unknown"
    platform: str = "unknown"
    scope: str = "unknown"
    import_status: str = "complete"

    # Temporal coverage
    effective_date: date | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None

    # Entity scope FKs
    unit_id: str | None = None
    property_id: str | None = Field(default=None, index=True)
    lease_id: str | None = None
    manager_id: str | None = Field(default=None, index=True)

    # LLM-extracted manager name from report title — informational only
    report_manager: str | None = None

    # Self-referential: the report this one supersedes
    source_document_id: str | None = None

    uploaded_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
