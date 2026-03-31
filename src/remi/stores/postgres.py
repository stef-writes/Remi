"""Postgres-backed PropertyStore using SQLModel + asyncpg."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from sqlmodel import SQLModel, select

from remi.db.tables import (
    LeaseRow,
    MaintenanceRequestRow,
    PortfolioRow,
    PropertyManagerRow,
    PropertyRow,
    TenantRow,
    UnitRow,
)
from remi.models.properties import (
    Address,
    Lease,
    LeaseStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
    OccupancyStatus,
    Portfolio,
    Priority,
    Property,
    PropertyManager,
    PropertyStore,
    PropertyType,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)

if TYPE_CHECKING:
    from pydantic import BaseModel
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_T = TypeVar("_T", bound=SQLModel)


# ---------------------------------------------------------------------------
# Row ↔ DTO conversion helpers
# ---------------------------------------------------------------------------


def _manager_from_row(row: PropertyManagerRow) -> PropertyManager:
    return PropertyManager(
        id=row.id,
        name=row.name,
        email=row.email,
        company=row.company,
        phone=row.phone,
        manager_tag=row.manager_tag,
        portfolio_ids=row.portfolio_ids,
        created_at=row.created_at,
    )


def _manager_to_row(m: PropertyManager) -> PropertyManagerRow:
    return PropertyManagerRow(
        id=m.id,
        name=m.name,
        email=m.email,
        company=m.company,
        phone=m.phone,
        manager_tag=m.manager_tag,
        portfolio_ids=list(m.portfolio_ids),
        created_at=m.created_at,
    )


def _portfolio_from_row(row: PortfolioRow) -> Portfolio:
    return Portfolio(
        id=row.id,
        manager_id=row.manager_id,
        name=row.name,
        description=row.description,
        property_ids=row.property_ids,
        created_at=row.created_at,
    )


def _portfolio_to_row(p: Portfolio) -> PortfolioRow:
    return PortfolioRow(
        id=p.id,
        manager_id=p.manager_id,
        name=p.name,
        description=p.description,
        property_ids=list(p.property_ids),
        created_at=p.created_at,
    )


def _property_from_row(row: PropertyRow) -> Property:
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
        created_at=row.created_at,
    )


def _property_to_row(p: Property) -> PropertyRow:
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
        created_at=p.created_at,
    )


def _unit_from_row(row: UnitRow) -> Unit:
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
    )


def _unit_to_row(u: Unit) -> UnitRow:
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
    )


def _lease_from_row(row: LeaseRow) -> Lease:
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
    )


def _lease_to_row(le: Lease) -> LeaseRow:
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
    )


def _tenant_from_row(row: TenantRow) -> Tenant:
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
        created_at=row.created_at,
    )


def _tenant_to_row(t: Tenant) -> TenantRow:
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
        created_at=t.created_at,
    )


def _maintenance_from_row(row: MaintenanceRequestRow) -> MaintenanceRequest:
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


def _maintenance_to_row(mr: MaintenanceRequest) -> MaintenanceRequestRow:
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


# ---------------------------------------------------------------------------
# Partial-update merge (mirrors InMemoryPropertyStore._merge semantics)
# ---------------------------------------------------------------------------


def _apply_merge(existing_row: _T, incoming_dto: BaseModel) -> _T:
    """Update only the columns that were explicitly set on the incoming Pydantic model.

    Preserves the same model_fields_set semantics as the in-memory store so
    that partial upserts from document ingestion work identically.
    """
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


# ---------------------------------------------------------------------------
# PostgresPropertyStore
# ---------------------------------------------------------------------------


class PostgresPropertyStore(PropertyStore):
    """PropertyStore backed by Postgres via SQLModel async sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # -- PropertyManager ----------------------------------------------------

    async def get_manager(self, manager_id: str) -> PropertyManager | None:
        async with self._session_factory() as session:
            row = await session.get(PropertyManagerRow, manager_id)
            return _manager_from_row(row) if row else None

    async def list_managers(self) -> list[PropertyManager]:
        async with self._session_factory() as session:
            result = await session.exec(select(PropertyManagerRow))
            return [_manager_from_row(r) for r in result.all()]

    async def upsert_manager(self, manager: PropertyManager) -> None:
        async with self._session_factory() as session:
            existing = await session.get(PropertyManagerRow, manager.id)
            if existing:
                _apply_merge(existing, manager)
                session.add(existing)
            else:
                session.add(_manager_to_row(manager))
            await session.commit()

    # -- Portfolio ----------------------------------------------------------

    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        async with self._session_factory() as session:
            row = await session.get(PortfolioRow, portfolio_id)
            return _portfolio_from_row(row) if row else None

    async def list_portfolios(self, *, manager_id: str | None = None) -> list[Portfolio]:
        async with self._session_factory() as session:
            stmt = select(PortfolioRow)
            if manager_id:
                stmt = stmt.where(PortfolioRow.manager_id == manager_id)
            result = await session.exec(stmt)
            return [_portfolio_from_row(r) for r in result.all()]

    async def upsert_portfolio(self, portfolio: Portfolio) -> None:
        async with self._session_factory() as session:
            existing = await session.get(PortfolioRow, portfolio.id)
            if existing:
                _apply_merge(existing, portfolio)
                session.add(existing)
            else:
                session.add(_portfolio_to_row(portfolio))
            await session.commit()

    # -- Property -----------------------------------------------------------

    async def get_property(self, property_id: str) -> Property | None:
        async with self._session_factory() as session:
            row = await session.get(PropertyRow, property_id)
            return _property_from_row(row) if row else None

    async def list_properties(self, *, portfolio_id: str | None = None) -> list[Property]:
        async with self._session_factory() as session:
            stmt = select(PropertyRow)
            if portfolio_id:
                stmt = stmt.where(PropertyRow.portfolio_id == portfolio_id)
            result = await session.exec(stmt)
            return [_property_from_row(r) for r in result.all()]

    async def upsert_property(self, prop: Property) -> None:
        async with self._session_factory() as session:
            existing = await session.get(PropertyRow, prop.id)
            if existing:
                _apply_merge(existing, prop)
                session.add(existing)
            else:
                session.add(_property_to_row(prop))
            await session.commit()

    # -- Unit ---------------------------------------------------------------

    async def get_unit(self, unit_id: str) -> Unit | None:
        async with self._session_factory() as session:
            row = await session.get(UnitRow, unit_id)
            return _unit_from_row(row) if row else None

    async def list_units(
        self,
        *,
        property_id: str | None = None,
        status: UnitStatus | None = None,
        occupancy_status: OccupancyStatus | None = None,
    ) -> list[Unit]:
        async with self._session_factory() as session:
            stmt = select(UnitRow)
            if property_id:
                stmt = stmt.where(UnitRow.property_id == property_id)
            if status:
                stmt = stmt.where(UnitRow.status == status.value)
            if occupancy_status:
                stmt = stmt.where(UnitRow.occupancy_status == occupancy_status.value)
            result = await session.exec(stmt)
            return [_unit_from_row(r) for r in result.all()]

    async def upsert_unit(self, unit: Unit) -> None:
        async with self._session_factory() as session:
            existing = await session.get(UnitRow, unit.id)
            if existing:
                _apply_merge(existing, unit)
                session.add(existing)
            else:
                session.add(_unit_to_row(unit))
            await session.commit()

    # -- Lease --------------------------------------------------------------

    async def get_lease(self, lease_id: str) -> Lease | None:
        async with self._session_factory() as session:
            row = await session.get(LeaseRow, lease_id)
            return _lease_from_row(row) if row else None

    async def list_leases(
        self,
        *,
        unit_id: str | None = None,
        tenant_id: str | None = None,
        property_id: str | None = None,
        status: LeaseStatus | None = None,
    ) -> list[Lease]:
        async with self._session_factory() as session:
            stmt = select(LeaseRow)
            if unit_id:
                stmt = stmt.where(LeaseRow.unit_id == unit_id)
            if tenant_id:
                stmt = stmt.where(LeaseRow.tenant_id == tenant_id)
            if property_id:
                stmt = stmt.where(LeaseRow.property_id == property_id)
            if status:
                stmt = stmt.where(LeaseRow.status == status.value)
            result = await session.exec(stmt)
            return [_lease_from_row(r) for r in result.all()]

    async def upsert_lease(self, lease: Lease) -> None:
        async with self._session_factory() as session:
            existing = await session.get(LeaseRow, lease.id)
            if existing:
                _apply_merge(existing, lease)
                session.add(existing)
            else:
                session.add(_lease_to_row(lease))
            await session.commit()

    # -- Tenant -------------------------------------------------------------

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        async with self._session_factory() as session:
            row = await session.get(TenantRow, tenant_id)
            return _tenant_from_row(row) if row else None

    async def list_tenants(
        self,
        *,
        property_id: str | None = None,
        status: TenantStatus | None = None,
    ) -> list[Tenant]:
        async with self._session_factory() as session:
            stmt = select(TenantRow)
            if property_id:
                lease_stmt = select(LeaseRow.tenant_id).where(LeaseRow.property_id == property_id)
                stmt = stmt.where(TenantRow.id.in_(lease_stmt))  # type: ignore[union-attr]
            if status:
                stmt = stmt.where(TenantRow.status == status.value)
            result = await session.exec(stmt)
            return [_tenant_from_row(r) for r in result.all()]

    async def upsert_tenant(self, tenant: Tenant) -> None:
        async with self._session_factory() as session:
            existing = await session.get(TenantRow, tenant.id)
            if existing:
                _apply_merge(existing, tenant)
                session.add(existing)
            else:
                session.add(_tenant_to_row(tenant))
            await session.commit()

    # -- Maintenance --------------------------------------------------------

    async def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None:
        async with self._session_factory() as session:
            row = await session.get(MaintenanceRequestRow, request_id)
            return _maintenance_from_row(row) if row else None

    async def list_maintenance_requests(
        self,
        *,
        property_id: str | None = None,
        unit_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]:
        async with self._session_factory() as session:
            stmt = select(MaintenanceRequestRow)
            if property_id:
                stmt = stmt.where(MaintenanceRequestRow.property_id == property_id)
            if unit_id:
                stmt = stmt.where(MaintenanceRequestRow.unit_id == unit_id)
            if status:
                stmt = stmt.where(MaintenanceRequestRow.status == status.value)
            result = await session.exec(stmt)
            return [_maintenance_from_row(r) for r in result.all()]

    async def upsert_maintenance_request(self, request: MaintenanceRequest) -> None:
        async with self._session_factory() as session:
            existing = await session.get(MaintenanceRequestRow, request.id)
            if existing:
                _apply_merge(existing, request)
                session.add(existing)
            else:
                session.add(_maintenance_to_row(request))
            await session.commit()
