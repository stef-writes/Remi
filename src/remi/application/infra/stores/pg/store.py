"""PostgresPropertyStore — full PropertyStore backed by Postgres via SQLModel."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from remi.application.core.models import (
    ActionItem,
    ActionItemStatus,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    MaintenanceStatus,
    Note,
    NoteProvenance,
    OccupancyStatus,
    Portfolio,
    Property,
    PropertyManager,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)
from remi.application.core.protocols import PropertyStore
from remi.application.infra.stores.pg.converters import (
    action_item_from_row,
    action_item_to_row,
    apply_merge,
    lease_from_row,
    lease_to_row,
    maintenance_from_row,
    maintenance_to_row,
    manager_from_row,
    manager_to_row,
    note_from_row,
    note_to_row,
    portfolio_from_row,
    portfolio_to_row,
    property_from_row,
    property_to_row,
    tenant_from_row,
    tenant_to_row,
    unit_from_row,
    unit_to_row,
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
from remi.types.result import WriteOutcome, WriteResult


class PostgresPropertyStore(PropertyStore):
    """PropertyStore backed by Postgres via SQLModel async sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # -- PropertyManager ----------------------------------------------------

    async def get_manager(self, manager_id: str) -> PropertyManager | None:
        async with self._session_factory() as session:
            row = await session.get(PropertyManagerRow, manager_id)
            return manager_from_row(row) if row else None

    async def list_managers(self) -> list[PropertyManager]:
        async with self._session_factory() as session:
            result = await session.execute(select(PropertyManagerRow))
            return [manager_from_row(r) for r in result.scalars().all()]

    async def upsert_manager(self, manager: PropertyManager) -> WriteResult[PropertyManager]:
        async with self._session_factory() as session:
            existing = await session.get(PropertyManagerRow, manager.id)
            if existing:
                apply_merge(existing, manager)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(entity=manager_from_row(existing), outcome=WriteOutcome.UPDATED)
            session.add(manager_to_row(manager))
            await session.commit()
            return WriteResult(entity=manager, outcome=WriteOutcome.CREATED)

    async def delete_manager(self, manager_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(PropertyManagerRow, manager_id)
            if not row:
                return False
            pf_result = await session.execute(
                select(PortfolioRow).where(PortfolioRow.manager_id == manager_id)
            )
            pf_ids = [pf.id for pf in pf_result.scalars().all()]
            if pf_ids:
                prop_result = await session.execute(
                    select(PropertyRow).where(PropertyRow.portfolio_id.in_(pf_ids))  # type: ignore[union-attr]
                )
                for prop in prop_result.scalars().all():
                    prop.portfolio_id = ""
                    session.add(prop)
                for pf_id in pf_ids:
                    pf_row = await session.get(PortfolioRow, pf_id)
                    if pf_row:
                        await session.delete(pf_row)
            await session.delete(row)
            await session.commit()
            return True

    # -- Portfolio ----------------------------------------------------------

    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        async with self._session_factory() as session:
            row = await session.get(PortfolioRow, portfolio_id)
            return portfolio_from_row(row) if row else None

    async def list_portfolios(self, *, manager_id: str | None = None) -> list[Portfolio]:
        async with self._session_factory() as session:
            stmt = select(PortfolioRow)
            if manager_id:
                stmt = stmt.where(PortfolioRow.manager_id == manager_id)
            result = await session.execute(stmt)
            return [portfolio_from_row(r) for r in result.scalars().all()]

    async def upsert_portfolio(self, portfolio: Portfolio) -> WriteResult[Portfolio]:
        async with self._session_factory() as session:
            existing = await session.get(PortfolioRow, portfolio.id)
            if existing:
                apply_merge(existing, portfolio)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(
                    entity=portfolio_from_row(existing),
                    outcome=WriteOutcome.UPDATED,
                )
            session.add(portfolio_to_row(portfolio))
            await session.commit()
            return WriteResult(entity=portfolio, outcome=WriteOutcome.CREATED)

    # -- Property -----------------------------------------------------------

    async def get_property(self, property_id: str) -> Property | None:
        async with self._session_factory() as session:
            row = await session.get(PropertyRow, property_id)
            return property_from_row(row) if row else None

    async def list_properties(self, *, portfolio_id: str | None = None) -> list[Property]:
        async with self._session_factory() as session:
            stmt = select(PropertyRow)
            if portfolio_id:
                stmt = stmt.where(PropertyRow.portfolio_id == portfolio_id)
            result = await session.execute(stmt)
            return [property_from_row(r) for r in result.scalars().all()]

    async def upsert_property(self, prop: Property) -> WriteResult[Property]:
        async with self._session_factory() as session:
            existing = await session.get(PropertyRow, prop.id)
            if existing:
                apply_merge(existing, prop)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                entity = property_from_row(existing)
                return WriteResult(entity=entity, outcome=WriteOutcome.UPDATED)
            session.add(property_to_row(prop))
            await session.commit()
            return WriteResult(entity=prop, outcome=WriteOutcome.CREATED)

    async def delete_property(self, property_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(PropertyRow, property_id)
            if not row:
                return False
            for tbl in (UnitRow, LeaseRow):
                result = await session.execute(
                    select(tbl).where(tbl.property_id == property_id)  # type: ignore[attr-defined]
                )
                for child in result.scalars().all():
                    await session.delete(child)
            await session.delete(row)
            await session.commit()
            return True

    # -- Unit ---------------------------------------------------------------

    async def get_unit(self, unit_id: str) -> Unit | None:
        async with self._session_factory() as session:
            row = await session.get(UnitRow, unit_id)
            return unit_from_row(row) if row else None

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
            result = await session.execute(stmt)
            return [unit_from_row(r) for r in result.scalars().all()]

    async def upsert_unit(self, unit: Unit) -> WriteResult[Unit]:
        async with self._session_factory() as session:
            existing = await session.get(UnitRow, unit.id)
            if existing:
                apply_merge(existing, unit)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(entity=unit_from_row(existing), outcome=WriteOutcome.UPDATED)
            session.add(unit_to_row(unit))
            await session.commit()
            return WriteResult(entity=unit, outcome=WriteOutcome.CREATED)

    async def delete_units_by_property(self, property_id: str) -> int:
        async with self._session_factory() as session:
            stmt = select(UnitRow).where(UnitRow.property_id == property_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                await session.delete(row)
            await session.commit()
            return len(rows)

    # -- Lease --------------------------------------------------------------

    async def get_lease(self, lease_id: str) -> Lease | None:
        async with self._session_factory() as session:
            row = await session.get(LeaseRow, lease_id)
            return lease_from_row(row) if row else None

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
            result = await session.execute(stmt)
            return [lease_from_row(r) for r in result.scalars().all()]

    async def upsert_lease(self, lease: Lease) -> WriteResult[Lease]:
        async with self._session_factory() as session:
            existing = await session.get(LeaseRow, lease.id)
            if existing:
                apply_merge(existing, lease)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(entity=lease_from_row(existing), outcome=WriteOutcome.UPDATED)
            session.add(lease_to_row(lease))
            await session.commit()
            return WriteResult(entity=lease, outcome=WriteOutcome.CREATED)

    async def delete_leases_by_property(self, property_id: str) -> int:
        async with self._session_factory() as session:
            stmt = select(LeaseRow).where(LeaseRow.property_id == property_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                await session.delete(row)
            await session.commit()
            return len(rows)

    # -- Tenant -------------------------------------------------------------

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        async with self._session_factory() as session:
            row = await session.get(TenantRow, tenant_id)
            return tenant_from_row(row) if row else None

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
            result = await session.execute(stmt)
            return [tenant_from_row(r) for r in result.scalars().all()]

    async def upsert_tenant(self, tenant: Tenant) -> WriteResult[Tenant]:
        async with self._session_factory() as session:
            existing = await session.get(TenantRow, tenant.id)
            if existing:
                apply_merge(existing, tenant)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(entity=tenant_from_row(existing), outcome=WriteOutcome.UPDATED)
            session.add(tenant_to_row(tenant))
            await session.commit()
            return WriteResult(entity=tenant, outcome=WriteOutcome.CREATED)

    async def delete_tenant(self, tenant_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(TenantRow, tenant_id)
            if not row:
                return False
            result = await session.execute(select(LeaseRow).where(LeaseRow.tenant_id == tenant_id))
            for lease in result.scalars().all():
                await session.delete(lease)
            await session.delete(row)
            await session.commit()
            return True

    # -- Maintenance --------------------------------------------------------

    async def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None:
        async with self._session_factory() as session:
            row = await session.get(MaintenanceRequestRow, request_id)
            return maintenance_from_row(row) if row else None

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
            result = await session.execute(stmt)
            return [maintenance_from_row(r) for r in result.scalars().all()]

    async def upsert_maintenance_request(
        self,
        request: MaintenanceRequest,
    ) -> WriteResult[MaintenanceRequest]:
        async with self._session_factory() as session:
            existing = await session.get(MaintenanceRequestRow, request.id)
            if existing:
                apply_merge(existing, request)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(
                    entity=maintenance_from_row(existing),
                    outcome=WriteOutcome.UPDATED,
                )
            session.add(maintenance_to_row(request))
            await session.commit()
            return WriteResult(entity=request, outcome=WriteOutcome.CREATED)

    # -- Action Items -------------------------------------------------------

    async def get_action_item(self, item_id: str) -> ActionItem | None:
        async with self._session_factory() as session:
            row = await session.get(ActionItemRow, item_id)
            return action_item_from_row(row) if row else None

    async def list_action_items(
        self,
        *,
        manager_id: str | None = None,
        property_id: str | None = None,
        tenant_id: str | None = None,
        status: ActionItemStatus | None = None,
    ) -> list[ActionItem]:
        async with self._session_factory() as session:
            stmt = select(ActionItemRow)
            if manager_id:
                stmt = stmt.where(ActionItemRow.manager_id == manager_id)
            if property_id:
                stmt = stmt.where(ActionItemRow.property_id == property_id)
            if tenant_id:
                stmt = stmt.where(ActionItemRow.tenant_id == tenant_id)
            if status:
                stmt = stmt.where(ActionItemRow.status == status.value)
            result = await session.execute(stmt)
            return [action_item_from_row(r) for r in result.scalars().all()]

    async def upsert_action_item(self, item: ActionItem) -> WriteResult[ActionItem]:
        async with self._session_factory() as session:
            existing = await session.get(ActionItemRow, item.id)
            if existing:
                apply_merge(existing, item)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(
                    entity=action_item_from_row(existing),
                    outcome=WriteOutcome.UPDATED,
                )
            session.add(action_item_to_row(item))
            await session.commit()
            return WriteResult(entity=item, outcome=WriteOutcome.CREATED)

    async def delete_action_item(self, item_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(ActionItemRow, item_id)
            if not row:
                return False
            await session.delete(row)
            await session.commit()
            return True

    # -- Notes ----------------------------------------------------------------

    async def get_note(self, note_id: str) -> Note | None:
        async with self._session_factory() as session:
            row = await session.get(NoteRow, note_id)
            return note_from_row(row) if row else None

    async def list_notes(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        provenance: NoteProvenance | None = None,
    ) -> list[Note]:
        async with self._session_factory() as session:
            stmt = select(NoteRow)
            if entity_type:
                stmt = stmt.where(NoteRow.entity_type == entity_type)
            if entity_id:
                stmt = stmt.where(NoteRow.entity_id == entity_id)
            if provenance:
                stmt = stmt.where(NoteRow.provenance == provenance.value)
            result = await session.execute(stmt)
            return [note_from_row(r) for r in result.scalars().all()]

    async def upsert_note(self, note: Note) -> WriteResult[Note]:
        async with self._session_factory() as session:
            existing = await session.get(NoteRow, note.id)
            if existing:
                apply_merge(existing, note)
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return WriteResult(entity=note_from_row(existing), outcome=WriteOutcome.UPDATED)
            session.add(note_to_row(note))
            await session.commit()
            return WriteResult(entity=note, outcome=WriteOutcome.CREATED)

    async def delete_note(self, note_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(NoteRow, note_id)
            if not row:
                return False
            await session.delete(row)
            await session.commit()
            return True
