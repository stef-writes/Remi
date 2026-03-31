"""AppFolio Delinquency report ingestion."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from remi.documents.appfolio_schema import parse_delinquency_rows
from remi.knowledge.ingestion.helpers import parse_address
from remi.models.memory import KnowledgeStore, Relationship
from remi.models.properties import (
    Lease,
    OccupancyStatus,
    PropertyStore,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)
from remi.shared.text import slugify

if TYPE_CHECKING:
    from remi.knowledge.ingestion.base import IngestionResult
    from remi.models.documents import Document

_TENANT_STATUS_MAP: dict[str, TenantStatus] = {
    "current": TenantStatus.CURRENT,
    "notice": TenantStatus.NOTICE,
    "evict": TenantStatus.EVICT,
}


async def ingest_delinquency(
    doc: Document,
    namespace: str,
    result: IngestionResult,
    kb: KnowledgeStore,
    ps: PropertyStore,
    upsert_entity: Any,
    upsert_property_safe: Any,
    upload_portfolio_id: str | None = None,
) -> None:
    parsed_rows = parse_delinquency_rows(doc.rows)

    for row in parsed_rows:
        prop_id = slugify(f"property:{row.property_name}")
        unit_id = slugify(f"unit:{row.property_name}:{row.unit_number or 'main'}")
        tenant_id = slugify(f"tenant:{row.tenant_name}:{row.property_name}")

        await upsert_entity(
            prop_id,
            "appfolio_property",
            namespace,
            {"address": row.property_address, "name": row.property_name, "source_doc": doc.id},
            result,
        )
        await upsert_entity(
            unit_id,
            "appfolio_unit",
            namespace,
            {
                "property_name": row.property_name,
                "unit_number": row.unit_number,
                "source_doc": doc.id,
            },
            result,
        )

        tenant_props: dict[str, Any] = {
            "name": row.tenant_name,
            "tenant_status": row.tenant_status,
            "monthly_rent": row.monthly_rent,
            "amount_owed": row.amount_owed,
            "subsidy_delinquent": row.subsidy_delinquent,
            "balance_0_30": row.balance_0_30,
            "balance_30_plus": row.balance_30_plus,
            "source_doc": doc.id,
        }
        if row.tags:
            tenant_props["tags"] = row.tags
        if row.last_payment_date:
            tenant_props["last_payment_date"] = row.last_payment_date.isoformat()
        if row.delinquency_notes:
            tenant_props["delinquency_notes"] = row.delinquency_notes

        await upsert_entity(
            tenant_id, "appfolio_delinquent_tenant", namespace, tenant_props, result
        )

        for src, rel, tgt in [
            (unit_id, "belongs_to", prop_id),
            (tenant_id, "occupies", unit_id),
            (tenant_id, "owes_balance_at", prop_id),
        ]:
            await kb.put_relationship(
                Relationship(source_id=src, target_id=tgt, relation_type=rel, namespace=namespace)
            )
            result.relationships_created += 1

        addr = parse_address(row.property_address)
        await upsert_property_safe(
            prop_id, row.property_name, addr, portfolio_id=upload_portfolio_id
        )

        await ps.upsert_unit(
            Unit(
                id=unit_id,
                property_id=prop_id,
                unit_number=row.unit_number or "main",
                status=UnitStatus.OCCUPIED,
                occupancy_status=OccupancyStatus.OCCUPIED,
                current_rent=Decimal(str(row.monthly_rent)) if row.monthly_rent else Decimal("0"),
            )
        )

        tenant_status = _TENANT_STATUS_MAP.get(
            row.tenant_status.strip().lower(), TenantStatus.CURRENT
        )
        tags: list[str] = [t.strip() for t in (row.tags or "").split(",") if t.strip()]
        last_payment: date | None = row.last_payment_date.date() if row.last_payment_date else None

        await ps.upsert_tenant(
            Tenant(
                id=tenant_id,
                name=row.tenant_name,
                status=tenant_status,
                balance_owed=Decimal(str(row.amount_owed)),
                balance_0_30=Decimal(str(row.balance_0_30)),
                balance_30_plus=Decimal(str(row.balance_30_plus)),
                last_payment_date=last_payment,
                tags=tags,
            )
        )

        lease_id = slugify(
            f"lease:{row.tenant_name}:{row.property_name}:{row.unit_number or 'main'}"
        )
        await ps.upsert_lease(
            Lease(
                id=lease_id,
                unit_id=unit_id,
                tenant_id=tenant_id,
                property_id=prop_id,
                start_date=date(2000, 1, 1),
                end_date=date(2099, 12, 31),
                monthly_rent=Decimal(str(row.monthly_rent)) if row.monthly_rent else Decimal("0"),
            )
        )
