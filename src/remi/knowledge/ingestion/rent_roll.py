"""AppFolio Rent Roll ingestion."""

from __future__ import annotations

from typing import Any

from remi.documents.appfolio_schema import parse_rent_roll_rows
from remi.knowledge.ingestion.base import IngestionResult
from remi.knowledge.ingestion.helpers import occupancy_to_unit_status, parse_address
from remi.models.documents import Document
from remi.models.memory import KnowledgeStore, Relationship
from remi.models.properties import OccupancyStatus, PropertyStore, Unit
from remi.shared.text import slugify

_OCCUPANCY_MAP: dict[str, OccupancyStatus] = {
    "occupied": OccupancyStatus.OCCUPIED,
    "notice_rented": OccupancyStatus.NOTICE_RENTED,
    "notice_unrented": OccupancyStatus.NOTICE_UNRENTED,
    "vacant_rented": OccupancyStatus.VACANT_RENTED,
    "vacant_unrented": OccupancyStatus.VACANT_UNRENTED,
}


async def ingest_rent_roll(
    doc: Document,
    namespace: str,
    result: IngestionResult,
    kb: KnowledgeStore,
    ps: PropertyStore,
    upsert_entity: Any,
    upsert_property_safe: Any,
    upload_portfolio_id: str | None = None,
) -> None:
    parsed_rows = parse_rent_roll_rows(doc.rows)

    for row in parsed_rows:
        prop_id = slugify(f"property:{row.property_name}")
        unit_id = slugify(f"unit:{row.property_name}:{row.unit_number or 'main'}")

        await upsert_entity(
            prop_id,
            "appfolio_property",
            namespace,
            {"address": row.property_address, "name": row.property_name, "source_doc": doc.id},
            result,
        )

        unit_props: dict[str, Any] = {
            "property_name": row.property_name,
            "unit_number": row.unit_number,
            "occupancy_status": row.occupancy_status,
            "source_doc": doc.id,
        }
        if row.bedrooms is not None:
            unit_props["bedrooms"] = row.bedrooms
        if row.bathrooms is not None:
            unit_props["bathrooms"] = row.bathrooms
        if row.lease_start is not None:
            unit_props["lease_start"] = row.lease_start.isoformat()
        if row.lease_end is not None:
            unit_props["lease_end"] = row.lease_end.isoformat()
        if row.days_vacant is not None:
            unit_props["days_vacant"] = row.days_vacant
        if row.notes:
            unit_props["notes"] = row.notes
        unit_props["posted_website"] = row.posted_website
        unit_props["posted_internet"] = row.posted_internet

        await upsert_entity(unit_id, "appfolio_unit", namespace, unit_props, result)
        await kb.put_relationship(
            Relationship(
                source_id=unit_id,
                target_id=prop_id,
                relation_type="belongs_to",
                namespace=namespace,
            )
        )
        result.relationships_created += 1

        occupancy = _OCCUPANCY_MAP.get(row.occupancy_status)
        unit_status = occupancy_to_unit_status(occupancy)
        addr = parse_address(row.property_address)
        await upsert_property_safe(
            prop_id, row.property_name, addr, portfolio_id=upload_portfolio_id
        )

        await ps.upsert_unit(
            Unit(
                id=unit_id,
                property_id=prop_id,
                unit_number=row.unit_number or "main",
                bedrooms=row.bedrooms,
                bathrooms=row.bathrooms,
                status=unit_status,
                occupancy_status=occupancy,
                days_vacant=row.days_vacant,
                listed_on_website=row.posted_website,
                listed_on_internet=row.posted_internet,
            )
        )
