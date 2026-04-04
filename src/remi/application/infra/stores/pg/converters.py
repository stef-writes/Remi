"""Row ↔ DTO conversion helpers and partial-update merge for Postgres store."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel
from sqlmodel import SQLModel

from remi.application.core.models import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
    Address,
    Lease,
    LeaseStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
    Note,
    NoteProvenance,
    OccupancyStatus,
    Portfolio,
    Priority,
    Property,
    PropertyManager,
    PropertyType,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)
from remi.application.infra.stores.pg.tables import (
    ActionItemRow,
    LeaseRow,
    MaintenanceRequestRow,
    NoteRow,
    PortfolioRow,
    PropertyManagerRow,
    PropertyRow,
    TenantRow,
    UnitRow,
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
        portfolio_ids=row.portfolio_ids,
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
        portfolio_ids=list(m.portfolio_ids),
        created_at=m.created_at,
    )


def portfolio_from_row(row: PortfolioRow) -> Portfolio:
    from remi.application.core.models.enums import AssetClass

    return Portfolio(
        id=row.id,
        manager_id=row.manager_id,
        name=row.name,
        description=row.description,
        asset_class=AssetClass(row.asset_class) if row.asset_class else None,
        strategy=row.strategy,
        target_occupancy=row.target_occupancy,
        market=row.market,
        property_ids=row.property_ids,
        created_at=row.created_at,
    )


def portfolio_to_row(p: Portfolio) -> PortfolioRow:
    return PortfolioRow(
        id=p.id,
        manager_id=p.manager_id,
        name=p.name,
        description=p.description,
        asset_class=p.asset_class.value if p.asset_class else None,
        strategy=p.strategy,
        target_occupancy=p.target_occupancy,
        market=p.market,
        property_ids=list(p.property_ids),
        created_at=p.created_at,
    )


def property_from_row(row: PropertyRow) -> Property:
    return Property(
        id=row.id,
        portfolio_id=row.portfolio_id,
        name=row.name,
        address=Address(
            street=row.address_street,
            city=row.address_city,
            state=row.address_state,
            zip_code=row.address_zip_code,
            country=row.address_country,
        ),
        property_type=PropertyType(row.property_type),
        year_built=row.year_built,
        source_document_id=row.source_document_id,
        created_at=row.created_at,
    )


def property_to_row(p: Property) -> PropertyRow:
    return PropertyRow(
        id=p.id,
        portfolio_id=p.portfolio_id,
        name=p.name,
        property_type=p.property_type.value,
        year_built=p.year_built,
        address_street=p.address.street,
        address_city=p.address.city,
        address_state=p.address.state,
        address_zip_code=p.address.zip_code,
        address_country=p.address.country,
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
        market_rent=row.market_rent,
        current_rent=row.current_rent,
        status=UnitStatus(row.status),
        occupancy_status=OccupancyStatus(row.occupancy_status) if row.occupancy_status else None,
        days_vacant=row.days_vacant,
        listed_on_website=row.listed_on_website,
        listed_on_internet=row.listed_on_internet,
        floor=row.floor,
        source_document_id=row.source_document_id,
    )


def unit_to_row(u: Unit) -> UnitRow:
    return UnitRow(
        id=u.id,
        property_id=u.property_id,
        unit_number=u.unit_number,
        bedrooms=u.bedrooms,
        bathrooms=u.bathrooms,
        sqft=u.sqft,
        market_rent=u.market_rent,
        current_rent=u.current_rent,
        status=u.status.value,
        occupancy_status=u.occupancy_status.value if u.occupancy_status else None,
        days_vacant=u.days_vacant,
        listed_on_website=u.listed_on_website,
        listed_on_internet=u.listed_on_internet,
        floor=u.floor,
        source_document_id=u.source_document_id,
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
        source_document_id=le.source_document_id,
    )


def tenant_from_row(row: TenantRow) -> Tenant:
    return Tenant(
        id=row.id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        status=TenantStatus(row.status),
        balance_owed=row.balance_owed,
        balance_0_30=row.balance_0_30,
        balance_30_plus=row.balance_30_plus,
        last_payment_date=row.last_payment_date,
        tags=row.tags,
        lease_ids=row.lease_ids,
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
        balance_owed=t.balance_owed,
        balance_0_30=t.balance_0_30,
        balance_30_plus=t.balance_30_plus,
        last_payment_date=t.last_payment_date,
        tags=list(t.tags),
        lease_ids=list(t.lease_ids),
        source_document_id=t.source_document_id,
        created_at=t.created_at,
    )


def maintenance_from_row(row: MaintenanceRequestRow) -> MaintenanceRequest:
    return MaintenanceRequest(
        id=row.id,
        unit_id=row.unit_id,
        property_id=row.property_id,
        tenant_id=row.tenant_id,
        category=MaintenanceCategory(row.category),
        priority=Priority(row.priority),
        title=row.title,
        description=row.description,
        status=MaintenanceStatus(row.status),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        cost=row.cost,
        vendor=row.vendor,
    )


def maintenance_to_row(mr: MaintenanceRequest) -> MaintenanceRequestRow:
    return MaintenanceRequestRow(
        id=mr.id,
        unit_id=mr.unit_id,
        property_id=mr.property_id,
        tenant_id=mr.tenant_id,
        category=mr.category.value,
        priority=mr.priority.value,
        title=mr.title,
        description=mr.description,
        status=mr.status.value,
        created_at=mr.created_at,
        resolved_at=mr.resolved_at,
        cost=mr.cost,
        vendor=mr.vendor,
    )


def action_item_from_row(row: ActionItemRow) -> ActionItem:
    return ActionItem(
        id=row.id,
        title=row.title,
        description=row.description,
        status=ActionItemStatus(row.status),
        priority=ActionItemPriority(row.priority),
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

        if field_name in ("status", "property_type", "category", "priority", "occupancy_status"):
            value = value.value if value is not None else None

        if field_name in ("portfolio_ids", "property_ids", "tags", "lease_ids"):
            value = list(value)

        updates[field_name] = value

    for col, val in updates.items():
        setattr(existing_row, col, val)
    return existing_row
