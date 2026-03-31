"""AppFolio Lease Expiration report ingestion."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from remi.documents.appfolio_schema import parse_lease_expiration_rows
from remi.knowledge.ingestion.base import IngestionResult
from remi.knowledge.ingestion.helpers import parse_address
from remi.models.documents import Document
from remi.models.memory import KnowledgeStore, Relationship
from remi.models.properties import Lease, OccupancyStatus, PropertyStore, Tenant, Unit, UnitStatus
from remi.shared.text import slugify


async def ingest_lease_expiration(
    doc: Document,
    namespace: str,
    result: IngestionResult,
    kb: KnowledgeStore,
    ps: PropertyStore,
    upsert_entity: Any,
    upsert_property_safe: Any,
    ensure_manager: Any,
    upload_portfolio_id: str | None = None,
) -> None:
    parsed_rows = parse_lease_expiration_rows(doc.rows)

    for row in parsed_rows:
        prop_id = slugify(f"property:{row.property_name}")
        unit_id = slugify(f"unit:{row.property_name}:{row.unit_number or 'main'}")
        tenant_id = slugify(f"tenant:{row.tenant_name}:{row.property_name}")
        lease_id = slugify(
            f"lease:{row.tenant_name}:{row.property_name}:{row.unit_number or 'main'}"
        )

        prop_props: dict[str, Any] = {
            "address": row.property_address,
            "name": row.property_name,
            "source_doc": doc.id,
        }
        if row.tags:
            prop_props["manager_tag"] = row.tags

        await upsert_entity(prop_id, "appfolio_property", namespace, prop_props, result)

        unit_kb_props: dict[str, Any] = {
            "property_name": row.property_name,
            "unit_number": row.unit_number,
            "monthly_rent": row.monthly_rent,
            "source_doc": doc.id,
        }
        if row.market_rent:
            unit_kb_props["market_rent"] = row.market_rent
        if row.sqft:
            unit_kb_props["sqft"] = row.sqft

        await upsert_entity(unit_id, "appfolio_unit", namespace, unit_kb_props, result)

        tenant_kb_props: dict[str, Any] = {
            "name": row.tenant_name,
            "monthly_rent": row.monthly_rent,
            "deposit": row.deposit,
            "is_month_to_month": row.is_month_to_month,
            "source_doc": doc.id,
        }
        if row.move_in_date:
            tenant_kb_props["move_in_date"] = row.move_in_date.isoformat()
        if row.lease_expires:
            tenant_kb_props["lease_expires"] = row.lease_expires.isoformat()
        if row.phone_numbers:
            tenant_kb_props["phone_numbers"] = row.phone_numbers

        await upsert_entity(tenant_id, "appfolio_tenant", namespace, tenant_kb_props, result)

        for src, rel, tgt in [
            (unit_id, "belongs_to", prop_id),
            (tenant_id, "leases", unit_id),
        ]:
            await kb.put_relationship(
                Relationship(source_id=src, target_id=tgt, relation_type=rel, namespace=namespace)
            )
            result.relationships_created += 1

        portfolio_id: str | None = upload_portfolio_id
        if portfolio_id is None:
            manager_tag = row.tags.strip() if row.tags else None
            if manager_tag:
                portfolio_id = await ensure_manager(manager_tag)

        addr = parse_address(row.property_address)
        await upsert_property_safe(prop_id, row.property_name, addr, portfolio_id=portfolio_id)

        has_active_lease = row.monthly_rent > 0 and row.tenant_name.strip() != ""
        unit_status = UnitStatus.OCCUPIED if has_active_lease else UnitStatus.VACANT
        occ_status = OccupancyStatus.OCCUPIED if has_active_lease else None

        await ps.upsert_unit(
            Unit(
                id=unit_id,
                property_id=prop_id,
                unit_number=row.unit_number or "main",
                sqft=row.sqft,
                current_rent=Decimal(str(row.monthly_rent)),
                market_rent=Decimal(str(row.market_rent)) if row.market_rent else Decimal("0"),
                status=unit_status,
                occupancy_status=occ_status,
            )
        )

        await ps.upsert_tenant(Tenant(id=tenant_id, name=row.tenant_name, phone=row.phone_numbers))

        start = row.move_in_date.date() if row.move_in_date else date(2000, 1, 1)
        end = row.lease_expires.date() if row.lease_expires else date(2099, 12, 31)

        await ps.upsert_lease(
            Lease(
                id=lease_id,
                unit_id=unit_id,
                tenant_id=tenant_id,
                property_id=prop_id,
                start_date=start,
                end_date=end,
                monthly_rent=Decimal(str(row.monthly_rent)),
                deposit=Decimal(str(row.deposit)),
                market_rent=Decimal(str(row.market_rent)) if row.market_rent else Decimal("0"),
                is_month_to_month=row.is_month_to_month,
            )
        )
