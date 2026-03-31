"""IngestionService — structured entity extraction from uploaded documents.

Two-tier extraction strategy:
  1. AppFolio-aware parsing: if the document matches a known AppFolio report
     type (rent roll, delinquency, lease expiration), use the exact column
     mappings and section-aware logic to produce richly typed entities.
  2. Generic heuristic fallback: for unknown documents, classify columns by
     regex patterns and extract generic entities. Unclassifiable rows are
     returned for optional LLM enrichment.

Domain model writes: in addition to the KnowledgeStore (used by agents),
the service upserts typed Pydantic domain models into PropertyStore.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from remi.domain.memory.ports import Entity, KnowledgeStore, Relationship
from remi.domain.properties.enums import OccupancyStatus, TenantStatus, UnitStatus
from remi.domain.properties.models import (
    Address,
    Lease,
    Portfolio,
    Property,
    PropertyManager,
    Tenant,
    Unit,
)
from remi.infrastructure.documents.appfolio_schema import (
    AppFolioReportType,
    detect_report_type,
    parse_delinquency_rows,
    parse_lease_expiration_rows,
    parse_property_name,
    parse_rent_roll_rows,
)

if TYPE_CHECKING:
    from remi.domain.documents.models import Document
    from remi.domain.properties.ports import PropertyStore

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Generic column-to-entity-type mapping rules (fallback for unknown docs)
# ---------------------------------------------------------------------------

_COLUMN_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("property",    re.compile(r"property|building|address|location|complex", re.I)),
    ("tenant",      re.compile(r"tenant|resident|occupant|renter|lessee", re.I)),
    ("unit",        re.compile(r"unit|apt|suite|apartment|room|space", re.I)),
    ("lease",       re.compile(r"lease|contract|agreement|term", re.I)),
    ("maintenance", re.compile(r"maintenance|repair|work.?order|service.?request|issue|ticket", re.I)),
    ("financial",   re.compile(r"rent|revenue|income|expense|cost|amount|payment|fee|price|noi", re.I)),
]

_RELATIONSHIP_RULES: list[tuple[str, str, str]] = [
    ("tenant", "unit", "occupies"),
    ("unit", "property", "belongs_to"),
    ("lease", "unit", "covers"),
    ("lease", "tenant", "signed_by"),
    ("maintenance", "unit", "affects"),
    ("maintenance", "property", "reported_at"),
    ("financial", "property", "recorded_for"),
    ("financial", "unit", "recorded_for"),
    ("financial", "tenant", "charged_to"),
]


_OCCUPANCY_MAP: dict[str, OccupancyStatus] = {
    "occupied": OccupancyStatus.OCCUPIED,
    "notice_rented": OccupancyStatus.NOTICE_RENTED,
    "notice_unrented": OccupancyStatus.NOTICE_UNRENTED,
    "vacant_rented": OccupancyStatus.VACANT_RENTED,
    "vacant_unrented": OccupancyStatus.VACANT_UNRENTED,
}

_TENANT_STATUS_MAP: dict[str, TenantStatus] = {
    "current": TenantStatus.CURRENT,
    "notice": TenantStatus.NOTICE,
    "evict": TenantStatus.EVICT,
}

@dataclass
class IngestionResult:
    """Result of ingesting a document into the knowledge graph."""

    document_id: str
    report_type: str = "unknown"
    entities_created: int = 0
    relationships_created: int = 0
    ambiguous_rows: list[dict[str, Any]] = field(default_factory=list)


class IngestionService:
    """Extracts entities and relationships from documents into a KnowledgeStore
    and upserts typed domain models into PropertyStore."""

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        property_store: PropertyStore,
    ) -> None:
        self._kb = knowledge_store
        self._ps = property_store

    async def _ensure_manager(self, manager_tag: str) -> str:
        """Create or retrieve a manager + portfolio for a given tag.

        Returns the ``portfolio_id``.

        Normalizes manager names so "Ryan Steen Management" and "Ryan Steen"
        resolve to the same manager/portfolio.
        """
        mgr_name = _manager_name_from_tag(manager_tag)
        manager_id = _slugify(f"manager:{mgr_name}")
        await self._ps.upsert_manager(PropertyManager(
            id=manager_id,
            name=mgr_name,
            manager_tag=manager_tag,
        ))
        portfolio_id = _slugify(f"portfolio:{mgr_name}")
        await self._ps.upsert_portfolio(Portfolio(
            id=portfolio_id,
            manager_id=manager_id,
            name=f"{mgr_name} Portfolio",
        ))
        return portfolio_id

    async def _upsert_property_safe(
        self,
        prop_id: str,
        name: str,
        addr: Address,
        portfolio_id: str | None = None,
    ) -> None:
        """Upsert a property, preserving an existing manager/portfolio assignment.

        ``portfolio_id`` comes from three possible sources (in priority order):
          1. Upload-level manager tag (user said who this report is for).
          2. Row-level manager tag (lease expiration Tags column).
          3. Already stored assignment from a prior upload.

        If none of the above apply (truly first-time unseen property with no
        manager context), we store ``portfolio_id=""`` — the property exists
        but the director needs to re-upload with a manager tag.  There is no
        fake "Unassigned" manager.
        """
        existing = await self._ps.get_property(prop_id)

        if portfolio_id is not None:
            effective_pid = portfolio_id
        elif existing is not None and existing.portfolio_id:
            effective_pid = existing.portfolio_id
        else:
            effective_pid = ""

        await self._ps.upsert_property(Property(
            id=prop_id,
            portfolio_id=effective_pid,
            name=name,
            address=addr,
        ))

    async def ingest(
        self,
        doc: Document,
        *,
        manager: str | None = None,
    ) -> IngestionResult:
        namespace = f"doc:{doc.id}"
        report_type = detect_report_type(doc.column_names)

        result = IngestionResult(
            document_id=doc.id,
            report_type=report_type.value,
        )

        await self._kb.put_entity(Entity(
            entity_id=f"document:{doc.id}",
            entity_type="document",
            namespace=namespace,
            properties={
                "filename": doc.filename,
                "content_type": doc.content_type,
                "row_count": doc.row_count,
                "columns": doc.column_names,
                "report_type": report_type.value,
            },
        ))
        result.entities_created += 1

        # When a manager is provided at upload time, resolve/create the
        # manager + portfolio up-front so every property in this file gets
        # assigned to them.
        upload_portfolio_id: str | None = None
        if manager:
            upload_portfolio_id = await self._ensure_manager(manager)

        if report_type == AppFolioReportType.RENT_ROLL:
            await self._ingest_rent_roll(doc, namespace, result, upload_portfolio_id)
        elif report_type == AppFolioReportType.DELINQUENCY:
            await self._ingest_delinquency(doc, namespace, result, upload_portfolio_id)
        elif report_type == AppFolioReportType.LEASE_EXPIRATION:
            await self._ingest_lease_expiration(doc, namespace, result, upload_portfolio_id)
        else:
            await self._ingest_generic(doc, namespace, result)

        logger.info(
            "ingestion_complete",
            doc_id=doc.id,
            report_type=report_type.value,
            entities=result.entities_created,
            relationships=result.relationships_created,
            ambiguous=len(result.ambiguous_rows),
        )
        return result

    # ------------------------------------------------------------------
    # AppFolio: Rent Roll
    # ------------------------------------------------------------------

    async def _ingest_rent_roll(
        self,
        doc: Document,
        namespace: str,
        result: IngestionResult,
        upload_portfolio_id: str | None = None,
    ) -> None:
        parsed_rows = parse_rent_roll_rows(doc.rows)

        for row in parsed_rows:
            prop_id = _slugify(f"property:{row.property_name}")
            unit_id = _slugify(f"unit:{row.property_name}:{row.unit_number or 'main'}")

            # --- KnowledgeStore ---
            await self._upsert_entity(prop_id, "appfolio_property", namespace, {
                "address": row.property_address,
                "name": row.property_name,
                "source_doc": doc.id,
            }, result)

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

            await self._upsert_entity(unit_id, "appfolio_unit", namespace, unit_props, result)
            await self._put_rel(unit_id, "belongs_to", prop_id, namespace, result)

            # --- PropertyStore ---
            occupancy = _OCCUPANCY_MAP.get(row.occupancy_status)
            unit_status = _occupancy_to_unit_status(occupancy)

            addr = _parse_address(row.property_address)
            await self._upsert_property_safe(
                prop_id, row.property_name, addr, portfolio_id=upload_portfolio_id,
            )

            await self._ps.upsert_unit(Unit(
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
            ))

    # ------------------------------------------------------------------
    # AppFolio: Delinquency
    # ------------------------------------------------------------------

    async def _ingest_delinquency(
        self,
        doc: Document,
        namespace: str,
        result: IngestionResult,
        upload_portfolio_id: str | None = None,
    ) -> None:
        parsed_rows = parse_delinquency_rows(doc.rows)

        for row in parsed_rows:
            prop_id = _slugify(f"property:{row.property_name}")
            unit_id = _slugify(f"unit:{row.property_name}:{row.unit_number or 'main'}")
            tenant_id = _slugify(f"tenant:{row.tenant_name}:{row.property_name}")

            # --- KnowledgeStore ---
            await self._upsert_entity(prop_id, "appfolio_property", namespace, {
                "address": row.property_address,
                "name": row.property_name,
                "source_doc": doc.id,
            }, result)

            await self._upsert_entity(unit_id, "appfolio_unit", namespace, {
                "property_name": row.property_name,
                "unit_number": row.unit_number,
                "source_doc": doc.id,
            }, result)

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

            await self._upsert_entity(tenant_id, "appfolio_delinquent_tenant", namespace, tenant_props, result)

            await self._put_rel(unit_id, "belongs_to", prop_id, namespace, result)
            await self._put_rel(tenant_id, "occupies", unit_id, namespace, result)
            await self._put_rel(tenant_id, "owes_balance_at", prop_id, namespace, result)

            # --- PropertyStore ---
            addr = _parse_address(row.property_address)
            await self._upsert_property_safe(
                prop_id, row.property_name, addr, portfolio_id=upload_portfolio_id,
            )

            await self._ps.upsert_unit(Unit(
                id=unit_id,
                property_id=prop_id,
                unit_number=row.unit_number or "main",
                status=UnitStatus.OCCUPIED,
                occupancy_status=OccupancyStatus.OCCUPIED,
                current_rent=Decimal(str(row.monthly_rent)) if row.monthly_rent else Decimal("0"),
            ))

            tenant_status = _TENANT_STATUS_MAP.get(
                row.tenant_status.strip().lower(), TenantStatus.CURRENT
            )
            tags: list[str] = [t.strip() for t in (row.tags or "").split(",") if t.strip()]
            last_payment: date | None = row.last_payment_date.date() if row.last_payment_date else None

            await self._ps.upsert_tenant(Tenant(
                id=tenant_id,
                name=row.tenant_name,
                status=tenant_status,
                balance_owed=Decimal(str(row.amount_owed)),
                balance_0_30=Decimal(str(row.balance_0_30)),
                balance_30_plus=Decimal(str(row.balance_30_plus)),
                last_payment_date=last_payment,
                tags=tags,
            ))

            lease_id = _slugify(f"lease:{row.tenant_name}:{row.property_name}:{row.unit_number or 'main'}")
            await self._ps.upsert_lease(Lease(
                id=lease_id,
                unit_id=unit_id,
                tenant_id=tenant_id,
                property_id=prop_id,
                start_date=date(2000, 1, 1),
                end_date=date(2099, 12, 31),
                monthly_rent=Decimal(str(row.monthly_rent)) if row.monthly_rent else Decimal("0"),
            ))

    # ------------------------------------------------------------------
    # AppFolio: Lease Expiration
    # ------------------------------------------------------------------

    async def _ingest_lease_expiration(
        self,
        doc: Document,
        namespace: str,
        result: IngestionResult,
        upload_portfolio_id: str | None = None,
    ) -> None:
        parsed_rows = parse_lease_expiration_rows(doc.rows)

        for row in parsed_rows:
            prop_id = _slugify(f"property:{row.property_name}")
            unit_id = _slugify(f"unit:{row.property_name}:{row.unit_number or 'main'}")
            tenant_id = _slugify(f"tenant:{row.tenant_name}:{row.property_name}")
            lease_id = _slugify(f"lease:{row.tenant_name}:{row.property_name}:{row.unit_number or 'main'}")

            # --- KnowledgeStore ---
            prop_props: dict[str, Any] = {
                "address": row.property_address,
                "name": row.property_name,
                "source_doc": doc.id,
            }
            if row.tags:
                prop_props["manager_tag"] = row.tags

            await self._upsert_entity(prop_id, "appfolio_property", namespace, prop_props, result)

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

            await self._upsert_entity(unit_id, "appfolio_unit", namespace, unit_kb_props, result)

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

            await self._upsert_entity(tenant_id, "appfolio_tenant", namespace, tenant_kb_props, result)

            await self._put_rel(unit_id, "belongs_to", prop_id, namespace, result)
            await self._put_rel(tenant_id, "leases", unit_id, namespace, result)

            # --- PropertyStore ---
            # Upload-level manager wins; fall back to row-level Tags column.
            portfolio_id: str | None = upload_portfolio_id

            if portfolio_id is None:
                manager_tag = row.tags.strip() if row.tags else None
                if manager_tag:
                    portfolio_id = await self._ensure_manager(manager_tag)

            addr = _parse_address(row.property_address)
            await self._upsert_property_safe(
                prop_id, row.property_name, addr, portfolio_id=portfolio_id,
            )

            has_active_lease = row.monthly_rent > 0 and row.tenant_name.strip() != ""
            unit_status = UnitStatus.OCCUPIED if has_active_lease else UnitStatus.VACANT
            occ_status = OccupancyStatus.OCCUPIED if has_active_lease else None

            await self._ps.upsert_unit(Unit(
                id=unit_id,
                property_id=prop_id,
                unit_number=row.unit_number or "main",
                sqft=row.sqft,
                current_rent=Decimal(str(row.monthly_rent)),
                market_rent=Decimal(str(row.market_rent)) if row.market_rent else Decimal("0"),
                status=unit_status,
                occupancy_status=occ_status,
            ))

            await self._ps.upsert_tenant(Tenant(
                id=tenant_id,
                name=row.tenant_name,
                phone=row.phone_numbers,
            ))

            start = row.move_in_date.date() if row.move_in_date else date(2000, 1, 1)
            end = row.lease_expires.date() if row.lease_expires else date(2099, 12, 31)

            await self._ps.upsert_lease(Lease(
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
            ))

    # ------------------------------------------------------------------
    # Generic fallback ingestion (KnowledgeStore only)
    # ------------------------------------------------------------------

    async def _ingest_generic(
        self,
        doc: Document,
        namespace: str,
        result: IngestionResult,
    ) -> None:
        col_map = _classify_columns_generic(doc.column_names)
        if not col_map:
            result.ambiguous_rows = list(doc.rows)
            logger.info(
                "no_columns_matched",
                doc_id=doc.id,
                columns=doc.column_names,
                ambiguous=len(doc.rows),
            )
            return

        for row_idx, row in enumerate(doc.rows):
            row_entities = await self._extract_generic_row(
                row, row_idx, col_map, namespace, doc.id, result
            )
            if not row_entities:
                result.ambiguous_rows.append(row)

            result.relationships_created += await self._infer_generic_relationships(
                row_entities, namespace
            )

    async def _extract_generic_row(
        self,
        row: dict[str, Any],
        row_idx: int,
        col_map: dict[str, str],
        namespace: str,
        doc_id: str,
        result: IngestionResult,
    ) -> dict[str, str]:
        type_to_props: dict[str, dict[str, Any]] = {}
        for col, val in row.items():
            entity_type = col_map.get(col)
            if entity_type is None or val is None:
                continue
            type_to_props.setdefault(entity_type, {})[col] = val

        row_entities: dict[str, str] = {}

        for entity_type, props in type_to_props.items():
            eid = _entity_id_from_row(entity_type, row, row_idx, doc_id)
            await self._upsert_entity(eid, entity_type, namespace, props, result)
            row_entities[entity_type] = eid

        return row_entities

    async def _infer_generic_relationships(
        self,
        row_entities: dict[str, str],
        namespace: str,
    ) -> int:
        count = 0
        for source_type, target_type, relation in _RELATIONSHIP_RULES:
            source_id = row_entities.get(source_type)
            target_id = row_entities.get(target_type)
            if source_id and target_id and source_id != target_id:
                await self._kb.put_relationship(Relationship(
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation,
                    namespace=namespace,
                ))
                count += 1
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        namespace: str,
        props: dict[str, Any],
        result: IngestionResult,
    ) -> None:
        existing = await self._kb.get_entity(namespace, entity_id)
        if existing:
            merged = {**existing.properties, **props}
            await self._kb.put_entity(Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                namespace=namespace,
                properties=merged,
            ))
        else:
            await self._kb.put_entity(Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                namespace=namespace,
                properties=props,
            ))
            result.entities_created += 1

    async def _put_rel(
        self,
        source_id: str,
        relation: str,
        target_id: str,
        namespace: str,
        result: IngestionResult,
    ) -> None:
        await self._kb.put_relationship(Relationship(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation,
            namespace=namespace,
        ))
        result.relationships_created += 1


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _classify_columns_generic(column_names: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for col in column_names:
        for entity_type, pattern in _COLUMN_RULES:
            if pattern.search(col):
                mapping[col] = entity_type
                break
    return mapping


def _entity_id_from_row(
    entity_type: str, row: dict[str, Any], row_idx: int, doc_id: str
) -> str:
    for key in ("id", f"{entity_type}_id", f"{entity_type}Id", "ID"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return f"{entity_type}:{val}"
    name_keys = ("name", f"{entity_type}_name", "title", "label")
    for key in name_keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            slug = re.sub(r"[^a-z0-9]+", "-", str(val).lower().strip())[:40]
            return f"{entity_type}:{slug}"
    return f"{entity_type}:{doc_id}:row-{row_idx}"


def _slugify(text: str) -> str:
    """Convert a string to a stable entity ID slug."""
    return re.sub(r"[^a-z0-9:]+", "-", text.lower().strip()).strip("-")


def _parse_address(full_address: str) -> Address:
    """Best-effort address parsing from AppFolio's combined address string."""
    name = parse_property_name(full_address)
    parts = full_address.rsplit(",", 1)
    city = "Pittsburgh"
    state = "PA"
    zip_code = ""
    if len(parts) >= 2:
        tail = parts[1].strip()
        state_zip = tail.split()
        if len(state_zip) >= 2:
            state = state_zip[0]
            zip_code = state_zip[1]
        elif len(state_zip) == 1:
            state = state_zip[0]
    return Address(street=name, city=city, state=state, zip_code=zip_code)


def _manager_name_from_tag(tag: str) -> str:
    """Extract the person's name from a manager tag like 'Jake Kraus Management'."""
    suffixes = ("management", "mgmt", "properties", "property")
    name = tag.strip()
    lower = name.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name or tag


def _occupancy_to_unit_status(occ: OccupancyStatus | None) -> UnitStatus:
    """Map AppFolio occupancy to the simpler UnitStatus enum."""
    if occ is None:
        return UnitStatus.VACANT
    if occ == OccupancyStatus.OCCUPIED:
        return UnitStatus.OCCUPIED
    if occ in (OccupancyStatus.NOTICE_RENTED, OccupancyStatus.NOTICE_UNRENTED):
        return UnitStatus.OCCUPIED
    return UnitStatus.VACANT
