"""Row ↔ DTO conversion helpers and partial-update merge for Postgres store."""

from __future__ import annotations

import contextlib
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlmodel import SQLModel

from remi.application.core.models import (
    ActionItem,
    ActionItemStatus,
    Address,
    AssetClass,
    BalanceObservation,
    DateRange,
    Document,
    DocumentType,
    ImportStatus,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    MaintenanceSource,
    MaintenanceStatus,
    Note,
    NoteProvenance,
    Owner,
    OwnerType,
    Platform,
    Priority,
    Property,
    PropertyManager,
    PropertyType,
    ReportScope,
    ReportType,
    Tenant,
    TenantStatus,
    TradeCategory,
    Unit,
    UnitType,
    Vendor,
)
from remi.application.infra.stores.pg.tables import (
    ActionItemRow,
    AppDocumentRow,
    BalanceObservationRow,
    LeaseRow,
    MaintenanceRequestRow,
    NoteRow,
    OwnerRow,
    PropertyManagerRow,
    PropertyRow,
    TenantRow,
    UnitRow,
    VendorRow,
)

_T = TypeVar("_T", bound=SQLModel)


def manager_from_row(row: PropertyManagerRow) -> PropertyManager:
    return PropertyManager(
        id=row.id,
        name=row.name,
        email=row.email,
        company=row.company,
        phone=row.phone,
        manager_tag=row.manager_tag,
        title=row.title,
        territory=row.territory,
        max_units=row.max_units,
        license_number=row.license_number,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def manager_to_row(m: PropertyManager) -> PropertyManagerRow:
    return PropertyManagerRow(
        id=m.id,
        name=m.name,
        email=m.email,
        company=m.company,
        phone=m.phone,
        manager_tag=m.manager_tag,
        title=m.title,
        territory=m.territory,
        max_units=m.max_units,
        license_number=m.license_number,
        source_document_id=m.source_document_id,
        created_at=m.created_at,
    )


def property_from_row(row: PropertyRow) -> Property:
    return Property(
        id=row.id,
        manager_id=row.manager_id,
        name=row.name,
        address=Address(
            street=row.address_street,
            city=row.address_city,
            state=row.address_state,
            zip_code=row.address_zip_code,
            country=row.address_country,
        ),
        property_type=(
            PropertyType.MULTI_FAMILY
            if row.property_type == "residential"
            else PropertyType(row.property_type)
        ),
        asset_class=_coerce_enum(AssetClass, row.asset_class, None) if row.asset_class else None,
        year_built=row.year_built,
        owner_id=row.owner_id,
        unit_count=row.unit_count,
        neighborhood=row.neighborhood,
        year_renovated=row.year_renovated,
        acquisition_date=row.acquisition_date,
        management_start_date=row.management_start_date,
        content_hash=row.content_hash,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def property_to_row(p: Property) -> PropertyRow:
    return PropertyRow(
        id=p.id,
        manager_id=p.manager_id,
        name=p.name,
        property_type=p.property_type.value,
        asset_class=p.asset_class.value if p.asset_class else None,
        year_built=p.year_built,
        owner_id=p.owner_id,
        unit_count=p.unit_count,
        neighborhood=p.neighborhood,
        year_renovated=p.year_renovated,
        acquisition_date=p.acquisition_date,
        management_start_date=p.management_start_date,
        address_street=p.address.street,
        address_city=p.address.city,
        address_state=p.address.state,
        address_zip_code=p.address.zip_code,
        address_country=p.address.country,
        content_hash=p.content_hash,
        source_document_id=p.source_document_id,
        created_at=p.created_at,
    )


def unit_from_row(row: UnitRow) -> Unit:
    return Unit(
        id=row.id,
        property_id=row.property_id,
        unit_number=row.unit_number,
        bedrooms=row.bedrooms,
        bathrooms=row.bathrooms,
        sqft=row.sqft,
        unit_type=UnitType(row.unit_type) if row.unit_type else None,
        floor=row.floor,
        market_rent=row.market_rent,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def unit_to_row(u: Unit) -> UnitRow:
    return UnitRow(
        id=u.id,
        property_id=u.property_id,
        unit_number=u.unit_number,
        bedrooms=u.bedrooms,
        bathrooms=u.bathrooms,
        sqft=u.sqft,
        unit_type=u.unit_type.value if u.unit_type else None,
        floor=u.floor,
        market_rent=u.market_rent,
        source_document_id=u.source_document_id,
        created_at=u.created_at,
    )


def lease_from_row(row: LeaseRow) -> Lease:
    return Lease(
        id=row.id,
        unit_id=row.unit_id,
        tenant_id=row.tenant_id,
        property_id=row.property_id,
        start_date=row.start_date,
        end_date=row.end_date,
        monthly_rent=row.monthly_rent,
        deposit=row.deposit,
        status=LeaseStatus(row.status),
        market_rent=row.market_rent,
        is_month_to_month=row.is_month_to_month,
        notice_date=row.notice_date,
        move_in_date=row.move_in_date,
        move_out_date=row.move_out_date,
        first_seen_at=row.first_seen_at,
        last_confirmed_at=row.last_confirmed_at,
        source_document_id=row.source_document_id,
    )


def lease_to_row(le: Lease) -> LeaseRow:
    return LeaseRow(
        id=le.id,
        unit_id=le.unit_id,
        tenant_id=le.tenant_id,
        property_id=le.property_id,
        start_date=le.start_date,
        end_date=le.end_date,
        monthly_rent=le.monthly_rent,
        deposit=le.deposit,
        status=le.status.value,
        market_rent=le.market_rent,
        is_month_to_month=le.is_month_to_month,
        notice_date=le.notice_date,
        move_in_date=le.move_in_date,
        move_out_date=le.move_out_date,
        first_seen_at=le.first_seen_at,
        last_confirmed_at=le.last_confirmed_at,
        source_document_id=le.source_document_id,
    )


def tenant_from_row(row: TenantRow) -> Tenant:
    return Tenant(
        id=row.id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        status=TenantStatus(row.status),
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def tenant_to_row(t: Tenant) -> TenantRow:
    return TenantRow(
        id=t.id,
        name=t.name,
        email=t.email,
        phone=t.phone,
        status=t.status.value,
        source_document_id=t.source_document_id,
        created_at=t.created_at,
    )


def balance_observation_from_row(row: BalanceObservationRow) -> BalanceObservation:
    return BalanceObservation(
        id=row.id,
        tenant_id=row.tenant_id,
        lease_id=row.lease_id,
        property_id=row.property_id,
        observed_at=row.observed_at,
        balance_total=row.balance_total,
        balance_0_30=row.balance_0_30,
        balance_30_plus=row.balance_30_plus,
        last_payment_date=row.last_payment_date,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def balance_observation_to_row(obs: BalanceObservation) -> BalanceObservationRow:
    return BalanceObservationRow(
        id=obs.id,
        tenant_id=obs.tenant_id,
        lease_id=obs.lease_id,
        property_id=obs.property_id,
        observed_at=obs.observed_at,
        balance_total=obs.balance_total,
        balance_0_30=obs.balance_0_30,
        balance_30_plus=obs.balance_30_plus,
        last_payment_date=obs.last_payment_date,
        source_document_id=obs.source_document_id,
        created_at=obs.created_at,
    )


def maintenance_from_row(row: MaintenanceRequestRow) -> MaintenanceRequest:
    return MaintenanceRequest(
        id=row.id,
        unit_id=row.unit_id,
        property_id=row.property_id,
        tenant_id=row.tenant_id,
        category=TradeCategory(row.category),
        priority=Priority(row.priority),
        source=MaintenanceSource(row.source) if row.source else None,
        title=row.title,
        description=row.description,
        status=MaintenanceStatus(row.status),
        scheduled_date=row.scheduled_date,
        completed_date=row.completed_date,
        resolved_at=row.resolved_at,
        sla_hours=row.sla_hours,
        cost=row.cost,
        vendor=row.vendor,
        vendor_id=row.vendor_id,
        content_hash=row.content_hash,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def maintenance_to_row(mr: MaintenanceRequest) -> MaintenanceRequestRow:
    return MaintenanceRequestRow(
        id=mr.id,
        unit_id=mr.unit_id,
        property_id=mr.property_id,
        tenant_id=mr.tenant_id,
        category=mr.category.value,
        priority=mr.priority.value,
        source=mr.source.value if mr.source else None,
        title=mr.title,
        description=mr.description,
        status=mr.status.value,
        scheduled_date=mr.scheduled_date,
        completed_date=mr.completed_date,
        resolved_at=mr.resolved_at,
        sla_hours=mr.sla_hours,
        cost=mr.cost,
        vendor=mr.vendor,
        vendor_id=mr.vendor_id,
        content_hash=mr.content_hash,
        source_document_id=mr.source_document_id,
        created_at=mr.created_at,
    )


def document_from_row(row: AppDocumentRow) -> Document:
    coverage: DateRange | None = None
    if row.coverage_start and row.coverage_end:
        with contextlib.suppress(ValueError):
            coverage = DateRange(start=row.coverage_start, end=row.coverage_end)

    return Document(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        content_hash=row.content_hash,
        document_type=DocumentType(row.document_type),
        kind=row.kind,
        page_count=row.page_count,
        chunk_count=row.chunk_count,
        row_count=row.row_count,
        size_bytes=row.size_bytes,
        tags=list(row.tags),
        report_type=_coerce_enum(ReportType, row.report_type, ReportType.UNKNOWN),
        platform=_coerce_enum(Platform, row.platform, Platform.UNKNOWN),
        scope=_coerce_enum(ReportScope, row.scope, ReportScope.UNKNOWN),
        import_status=_coerce_enum(ImportStatus, row.import_status, ImportStatus.COMPLETE),
        effective_date=row.effective_date,
        coverage=coverage,
        unit_id=row.unit_id,
        property_id=row.property_id,
        lease_id=row.lease_id,
        manager_id=row.manager_id,
        report_manager=row.report_manager,
        source_document_id=row.source_document_id,
        uploaded_at=row.uploaded_at,
    )


def document_to_row(doc: Document) -> AppDocumentRow:
    return AppDocumentRow(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        content_hash=doc.content_hash,
        document_type=doc.document_type.value,
        kind=doc.kind,
        page_count=doc.page_count,
        chunk_count=doc.chunk_count,
        row_count=doc.row_count,
        size_bytes=doc.size_bytes,
        tags=list(doc.tags),
        report_type=doc.report_type.value,
        platform=doc.platform.value,
        scope=doc.scope.value,
        import_status=doc.import_status.value,
        effective_date=doc.effective_date,
        coverage_start=doc.coverage.start if doc.coverage else None,
        coverage_end=doc.coverage.end if doc.coverage else None,
        unit_id=doc.unit_id,
        property_id=doc.property_id,
        lease_id=doc.lease_id,
        manager_id=doc.manager_id,
        report_manager=doc.report_manager,
        source_document_id=doc.source_document_id,
        uploaded_at=doc.uploaded_at,
    )


def _coerce_enum(enum_cls: type, raw: str, default: object) -> object:
    """Parse *raw* into *enum_cls*, falling back to *default* on unknown values."""
    try:
        return enum_cls(raw)
    except ValueError:
        return default


def action_item_from_row(row: ActionItemRow) -> ActionItem:
    return ActionItem(
        id=row.id,
        title=row.title,
        description=row.description,
        status=ActionItemStatus(row.status),
        priority=Priority(row.priority),
        manager_id=row.manager_id,
        property_id=row.property_id,
        tenant_id=row.tenant_id,
        due_date=row.due_date,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def action_item_to_row(item: ActionItem) -> ActionItemRow:
    return ActionItemRow(
        id=item.id,
        title=item.title,
        description=item.description,
        status=item.status.value,
        priority=item.priority.value,
        manager_id=item.manager_id,
        property_id=item.property_id,
        tenant_id=item.tenant_id,
        due_date=item.due_date,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def note_from_row(row: NoteRow) -> Note:
    return Note(
        id=row.id,
        content=row.content,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        provenance=NoteProvenance(row.provenance),
        source_doc=row.source_doc,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def note_to_row(note: Note) -> NoteRow:
    return NoteRow(
        id=note.id,
        content=note.content,
        entity_type=note.entity_type,
        entity_id=note.entity_id,
        provenance=note.provenance.value,
        source_doc=note.source_doc,
        created_by=note.created_by,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def owner_from_row(row: OwnerRow) -> Owner:
    addr: Address | None = None
    if row.address_street:
        addr = Address(
            street=row.address_street or "",
            city=row.address_city or "",
            state=row.address_state or "",
            zip_code=row.address_zip_code or "",
            country=row.address_country or "US",
        )
    return Owner(
        id=row.id,
        name=row.name,
        owner_type=_coerce_enum(OwnerType, row.owner_type, OwnerType.OTHER),
        company=row.company,
        email=row.email,
        phone=row.phone,
        address=addr,
        content_hash=row.content_hash,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def owner_to_row(o: Owner) -> OwnerRow:
    return OwnerRow(
        id=o.id,
        name=o.name,
        owner_type=o.owner_type.value,
        company=o.company,
        email=o.email,
        phone=o.phone,
        address_street=o.address.street if o.address else None,
        address_city=o.address.city if o.address else None,
        address_state=o.address.state if o.address else None,
        address_zip_code=o.address.zip_code if o.address else None,
        address_country=o.address.country if o.address else None,
        content_hash=o.content_hash,
        source_document_id=o.source_document_id,
        created_at=o.created_at,
    )


def vendor_from_row(row: VendorRow) -> Vendor:
    return Vendor(
        id=row.id,
        name=row.name,
        category=TradeCategory(row.category) if row.category else TradeCategory.GENERAL,
        phone=row.phone,
        email=row.email,
        is_internal=row.is_internal,
        license_number=row.license_number,
        insurance_expiry=row.insurance_expiry,
        rating=row.rating,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def vendor_to_row(v: Vendor) -> VendorRow:
    return VendorRow(
        id=v.id,
        name=v.name,
        category=v.category.value,
        phone=v.phone,
        email=v.email,
        is_internal=v.is_internal,
        license_number=v.license_number,
        insurance_expiry=v.insurance_expiry,
        rating=v.rating,
        source_document_id=v.source_document_id,
        created_at=v.created_at,
    )


def apply_merge(existing_row: _T, incoming_dto: BaseModel) -> _T:
    """Update only the columns that were explicitly set on the incoming Pydantic model."""
    explicitly_set = incoming_dto.model_fields_set
    if not explicitly_set:
        return existing_row

    updates: dict[str, Any] = {}
    for field_name in explicitly_set:
        value = getattr(incoming_dto, field_name)

        if field_name == "address" and isinstance(existing_row, PropertyRow):
            updates["address_street"] = value.street
            updates["address_city"] = value.city
            updates["address_state"] = value.state
            updates["address_zip_code"] = value.zip_code
            updates["address_country"] = value.country
            continue

        if field_name in (
            "status", "property_type", "category", "priority",
            "unit_type", "owner_type", "asset_class",
        ):
            value = value.value if value is not None else None

        updates[field_name] = value

    for col, val in updates.items():
        setattr(existing_row, col, val)
    return existing_row
