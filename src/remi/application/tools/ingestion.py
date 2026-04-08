"""Ingestion workflow tools — registered per-upload on the shared ToolRegistry.

The document_ingestion YAML workflow calls these as transform/for_each steps.
They are registered by ``register_ingestion_tools`` immediately before each
``WorkflowRunner.run`` call, closed over per-upload state.

Tool inventory (DAG order):
  initialize       — create IngestionCtx, resolve manager, stamp report_type
  merge_maps       — merge extract + inspect column maps (inspect wins)
  apply_column_map — rename columns, normalize addresses, section context
  validate_rows    — required-field checks, emit RowWarnings
  persist_row      — per-row entity persistence via ROW_PERSISTERS
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel as _BaseModel

from remi.agent.llm.types import ToolDefinition
from remi.agent.types import ToolRegistry
from remi.application.core.models import (
    BalanceObservation,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    MaintenanceStatus,
    Note,
    NoteProvenance,
    Owner,
    Priority,
    Property,
    PropertyManager,
    Tenant,
    TenantStatus,
    TradeCategory,
    Unit,
    Vendor,
)
from remi.application.core.models.enums import ReportType
from remi.application.core.protocols import PropertyStore
from remi.application.core.rules import manager_name_from_tag, normalize_entity_name
from remi.application.ingestion.models import (
    IngestionResult,
    ReviewItem,
    ReviewKind,
    ReviewOption,
    ReviewSeverity,
    RowWarning,
)
from remi.application.ingestion.rules import (
    is_junk_property,
    is_section_header,
    normalize_address,
    split_bd_ba,
)
from remi.types.identity import (
    balance_observation_id as _bal_obs_id,
    content_hash as _content_hash,
    lease_id as _lease_id,
    maintenance_id as _maintenance_id,
    manager_id as _manager_id,
    note_id as _note_id,
    owner_id as _owner_id,
    property_id as _property_id,
    tenant_id as _tenant_id,
    unit_id as _unit_id,
    vendor_id as _vendor_id,
)

_log = structlog.get_logger(__name__)

from remi.application.ingestion.rules import (
    LEASE_END_FALLBACK,
    LEASE_START_FALLBACK,
    MAINTENANCE_CATEGORY_MAP,
    MAINTENANCE_STATUS_MAP,
    PERSISTABLE_TYPES,
    PRIORITY_MAP,
    TENANT_STATUS_MAP,
    parse_address,
    property_name,
    to_date,
    to_decimal,
    to_int,
)


# ---------------------------------------------------------------------------
# ManagerResolver — find-or-create by tag
# ---------------------------------------------------------------------------


@dataclass
class ManagerResolution:
    manager_id: str
    manager_name: str
    created_new: bool = False
    alias_matched: bool = False
    alias_from: str | None = None
    alias_to: str | None = None


class ManagerResolver:
    """Resolves raw manager tags to PropertyManager entities."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store
        self._cache: dict[str, ManagerResolution] | None = None
        self._existing: list[PropertyManager] | None = None

    async def _ensure_loaded(self) -> list[PropertyManager]:
        if self._existing is None:
            self._existing = await self._ps.list_managers()
        return self._existing

    async def ensure_manager(self, tag: str) -> ManagerResolution:
        if self._cache and tag in self._cache:
            return self._cache[tag]

        display_name = manager_name_from_tag(tag)
        mid = _manager_id(display_name)
        existing_managers = await self._ensure_loaded()

        for mgr in existing_managers:
            if mgr.id == mid:
                resolution = ManagerResolution(manager_id=mgr.id, manager_name=mgr.name)
                self._set_cache(tag, resolution)
                return resolution

        tag_norm = normalize_entity_name(tag)
        for mgr in existing_managers:
            if normalize_entity_name(mgr.name) == tag_norm:
                resolution = ManagerResolution(
                    manager_id=mgr.id, manager_name=mgr.name,
                    alias_matched=True, alias_from=tag, alias_to=mgr.name,
                )
                self._set_cache(tag, resolution)
                return resolution

        manager = PropertyManager(id=mid, name=display_name, manager_tag=tag)
        await self._ps.upsert_manager(manager)
        self._existing = None
        _log.info("manager_created", manager_id=mid, manager_name=display_name, raw_tag=tag)
        resolution = ManagerResolution(manager_id=mid, manager_name=display_name, created_new=True)
        self._set_cache(tag, resolution)
        return resolution

    def _set_cache(self, tag: str, resolution: ManagerResolution) -> None:
        if self._cache is None:
            self._cache = {}
        self._cache[tag] = resolution


# ---------------------------------------------------------------------------
# IngestionCtx — shared mutable state across rows in a single document
# ---------------------------------------------------------------------------


class IngestionCtx:
    __slots__ = (
        "platform", "report_type", "doc_id", "namespace", "ps",
        "manager_resolver", "result", "upload_manager_id",
        "seen_properties", "prop_manager_tags", "real_manager_tags",
        "property_manager", "extracted_entity_ids",
    )

    def __init__(
        self, *, platform: str, report_type: ReportType, doc_id: str,
        namespace: str, ps: PropertyStore, manager_resolver: ManagerResolver,
        result: IngestionResult, upload_manager_id: str | None = None,
    ) -> None:
        self.platform = platform
        self.report_type = report_type
        self.doc_id = doc_id
        self.namespace = namespace
        self.ps = ps
        self.manager_resolver = manager_resolver
        self.result = result
        self.upload_manager_id = upload_manager_id
        self.seen_properties: set[str] = set()
        self.prop_manager_tags: dict[str, str] = {}
        self.real_manager_tags: set[str] = set()
        self.property_manager: dict[str, str] = {}
        self.extracted_entity_ids: list[tuple[str, str]] = []


async def _record_extracted(ctx: IngestionCtx, entity_id: str, entity_type: str) -> None:
    ctx.extracted_entity_ids.append((entity_id, entity_type))
    ctx.result.entities_created += 1


async def _ensure_property(row: dict[str, Any], ctx: IngestionCtx) -> str:
    raw_addr = str(row.get("property_address", "")).strip()
    name = property_name(raw_addr) or raw_addr
    prop_id = _property_id(name)

    if prop_id in ctx.seen_properties:
        return prop_id
    ctx.seen_properties.add(prop_id)

    existing = await ctx.ps.get_property(prop_id)
    mid: str | None = existing.manager_id if existing else None
    if ctx.upload_manager_id is not None:
        mid = ctx.upload_manager_id
    if prop_id in ctx.property_manager:
        mid = ctx.property_manager[prop_id]

    address = parse_address(raw_addr)
    tag = ctx.prop_manager_tags.get(prop_id)

    if tag and tag in ctx.real_manager_tags:
        resolution = await ctx.manager_resolver.ensure_manager(tag)
        ctx.property_manager[prop_id] = resolution.manager_id
        mid = resolution.manager_id
        if resolution.created_new:
            ctx.result.review_items.append(ReviewItem(
                kind=ReviewKind.MANAGER_INFERRED, severity=ReviewSeverity.INFO,
                message=f"Created new manager '{resolution.manager_name}' from tag '{tag}'",
                entity_type="PropertyManager", entity_id=resolution.manager_id,
            ))
        elif resolution.alias_matched:
            ctx.result.review_items.append(ReviewItem(
                kind=ReviewKind.ENTITY_MATCH, severity=ReviewSeverity.WARNING,
                message=f"Matched tag '{resolution.alias_from}' to existing manager '{resolution.alias_to}'",
                entity_type="PropertyManager", entity_id=resolution.manager_id,
                raw_value=resolution.alias_from, suggestion=resolution.alias_to,
                options=[
                    ReviewOption(id=resolution.manager_id, label=str(resolution.alias_to)),
                    ReviewOption(id="new", label=f"Create '{resolution.alias_from}' as new manager"),
                ],
            ))
    elif tag:
        ctx.result.manager_tags_skipped.append(tag)

    await ctx.ps.upsert_property(Property(
        id=prop_id, manager_id=mid, name=name, address=address,
        manager_tag=tag, source_document_id=ctx.doc_id,
    ))
    await _record_extracted(ctx, prop_id, "Property")
    return prop_id


# ---------------------------------------------------------------------------
# Column mapper
# ---------------------------------------------------------------------------


def apply_column_map(
    rows: list[dict[str, Any]], column_map: dict[str, str], entity_type: str,
    *, section_header_column: str | None = None,
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    current_property: str | None = None
    current_section: str | None = None
    total_skipped = 0

    for raw_row in rows:
        out: dict[str, Any] = {"type": entity_type}
        extra: dict[str, Any] = {}

        for raw_col, val in raw_row.items():
            if raw_col.startswith("_ctx_"):
                out[raw_col] = val
                continue
            if val is None:
                continue
            val_str = str(val).strip()
            if not val_str:
                continue
            mapped_field = column_map.get(raw_col)
            if mapped_field:
                out[mapped_field] = val
            else:
                extra[raw_col] = val

        if extra:
            out["extra_fields"] = extra

        bd_ba = out.pop("_bd_ba", None)
        if bd_ba is not None:
            beds, baths = split_bd_ba(str(bd_ba))
            if beds is not None and "bedrooms" not in out:
                out["bedrooms"] = beds
            if baths is not None and "bathrooms" not in out:
                out["bathrooms"] = baths

        ctx_prop = out.pop("_ctx_property_address", None)
        ctx_section = out.pop("_ctx_section_label", None)
        if ctx_prop:
            current_property = str(ctx_prop)
        if ctx_section:
            current_section = str(ctx_section)

        prop_val = str(out.get("property_address") or "").strip()
        if prop_val:
            normalized = normalize_address(prop_val)
            if is_section_header(out):
                current_property = normalized
                total_skipped += 1
                continue
            if is_junk_property(normalized):
                total_skipped += 1
                continue
            out["property_address"] = normalized
            current_property = normalized
        elif current_property:
            if is_junk_property(current_property):
                total_skipped += 1
                continue
            out["property_address"] = current_property

        if current_section:
            out.setdefault("_section_label", current_section)

        has_data = any(
            k not in ("type", "extra_fields", "_section_label") and v is not None
            for k, v in out.items()
        )
        if not has_data:
            total_skipped += 1
            continue

        mapped.append(out)

    if total_skipped:
        _log.info("mapper_skipped_rows", entity_type=entity_type, skipped=total_skipped, accepted=len(mapped))

    return mapped


# ---------------------------------------------------------------------------
# Row validator
# ---------------------------------------------------------------------------

_PERSISTER_REQUIREMENTS: dict[str, frozenset[str]] = {
    "Unit": frozenset({"property_address"}),
    "Tenant": frozenset({"property_address"}),
    "BalanceObservation": frozenset({"property_address"}),
    "Lease": frozenset({"property_address"}),
    "Property": frozenset({"property_address"}),
    "MaintenanceRequest": frozenset({"property_address"}),
    "Owner": frozenset(),
    "Vendor": frozenset(),
    "PropertyManager": frozenset(),
}


def _has_value(row: dict[str, Any], field: str) -> bool:
    if field == "property_address":
        for key in ("property_address", "address", "property_name", "_section_header"):
            val = row.get(key)
            if val is not None and str(val).strip():
                return True
        return False
    val = row.get(field)
    return val is not None and str(val).strip() != ""


def validate_rows(rows: list[dict[str, Any]], result: IngestionResult) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        entity_type = row.get("type", "")
        if entity_type not in PERSISTABLE_TYPES:
            result.observation_rows.append(row)
            result.rows_skipped += 1
            continue
        required = _PERSISTER_REQUIREMENTS.get(entity_type, frozenset())
        missing = [f for f in required if not _has_value(row, f)]
        if missing:
            for field_name in missing:
                result.validation_warnings.append(RowWarning(
                    row_index=idx, row_type=entity_type, field=field_name,
                    issue="required source field missing", raw_value="",
                ))
            result.rows_rejected += 1
            _log.info("row_rejected", row_index=idx, entity_type=entity_type, missing_fields=missing)
            continue
        accepted.append(row)
        result.rows_accepted += 1
    return accepted


# ---------------------------------------------------------------------------
# Persisters — per-entity-type row→store handlers
# ---------------------------------------------------------------------------


def _with_hash(entity: _BaseModel) -> _BaseModel:
    h = _content_hash(entity.model_dump(mode="json"))
    return entity.model_copy(update={"content_hash": h})


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _reconcile_lease(ctx: IngestionCtx, new_lease: Lease) -> None:
    existing_active = await ctx.ps.list_leases(unit_id=new_lease.unit_id, status=LeaseStatus.ACTIVE)
    for existing in existing_active:
        if existing.id == new_lease.id:
            continue
        if existing.tenant_id != new_lease.tenant_id:
            await ctx.ps.upsert_lease(existing.model_copy(update={"status": LeaseStatus.TERMINATED}))
    prior = await ctx.ps.get_lease(new_lease.id)
    now = _utcnow()
    update: dict[str, object] = {"last_confirmed_at": now}
    if prior is None:
        update["first_seen_at"] = now
    await ctx.ps.upsert_lease(new_lease.model_copy(update=update))  # type: ignore[arg-type]


async def persist_unit(row: dict[str, Any], ctx: IngestionCtx) -> None:
    mgr_tag = str(row.get("site_manager_name") or row.get("manager_name") or "").strip()
    if mgr_tag:
        raw_addr = str(row.get("property_address", "")).strip()
        pid = _property_id(property_name(raw_addr) or raw_addr)
        ctx.prop_manager_tags[pid] = mgr_tag
        ctx.real_manager_tags.add(mgr_tag)

    prop_id = await _ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)

    unit = Unit(
        id=uid, property_id=prop_id, unit_number=unum,
        bedrooms=to_int(row.get("bedrooms")),
        bathrooms=(float(row["bathrooms"]) if row.get("bathrooms") is not None else None),
        sqft=to_int(row.get("sqft")), market_rent=to_decimal(row.get("market_rent")),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_unit(_with_hash(unit))  # type: ignore[arg-type]
    await _record_extracted(ctx, uid, "Unit")

    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    rent = to_decimal(row.get("monthly_rent") or row.get("current_rent"))
    if tname and rent > 0:
        tid = _tenant_id(tname, prop_id)
        lid = _lease_id(tname, prop_id, unum)
        tenant = Tenant(id=tid, name=tname,
            phone=(str(row.get("phone_numbers") or row.get("phone") or "").strip() or None),
            source_document_id=ctx.doc_id)
        await ctx.ps.upsert_tenant(_with_hash(tenant))  # type: ignore[arg-type]
        await _record_extracted(ctx, tid, "Tenant")

        start = to_date(row.get("move_in_date") or row.get("start_date"))
        end = to_date(row.get("lease_expires") or row.get("end_date"))
        lease = Lease(
            id=lid, unit_id=uid, tenant_id=tid, property_id=prop_id,
            start_date=start or LEASE_START_FALLBACK, end_date=end or LEASE_END_FALLBACK,
            monthly_rent=rent, market_rent=to_decimal(row.get("market_rent")),
            deposit=to_decimal(row.get("deposit")),
            is_month_to_month=bool(row.get("is_month_to_month", False)),
            status=LeaseStatus.ACTIVE, source_document_id=ctx.doc_id,
        )
        await _reconcile_lease(ctx, _with_hash(lease))  # type: ignore[arg-type]
        await _record_extracted(ctx, lid, "Lease")


async def persist_tenant(row: dict[str, Any], ctx: IngestionCtx) -> None:
    prop_id = await _ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    tid = _tenant_id(tname, prop_id)
    lid = _lease_id(tname, prop_id, unum)

    await ctx.ps.upsert_unit(_with_hash(Unit(
        id=uid, property_id=prop_id, unit_number=unum, source_document_id=ctx.doc_id,
    )))  # type: ignore[arg-type]
    await _record_extracted(ctx, uid, "Unit")

    raw_st = row.get("tenant_status") or row.get("status") or "current"
    tenant = Tenant(id=tid, name=tname,
        status=TENANT_STATUS_MAP.get(str(raw_st).strip().lower(), TenantStatus.CURRENT),
        source_document_id=ctx.doc_id)
    await ctx.ps.upsert_tenant(_with_hash(tenant))  # type: ignore[arg-type]
    await _record_extracted(ctx, tid, "Tenant")

    lease = Lease(
        id=lid, unit_id=uid, tenant_id=tid, property_id=prop_id,
        start_date=LEASE_START_FALLBACK, end_date=LEASE_END_FALLBACK,
        monthly_rent=to_decimal(row.get("monthly_rent")),
        status=LeaseStatus.ACTIVE, source_document_id=ctx.doc_id,
    )
    await _reconcile_lease(ctx, _with_hash(lease))  # type: ignore[arg-type]
    await _record_extracted(ctx, lid, "Lease")

    obs_id = _bal_obs_id(tid, ctx.doc_id)
    obs = BalanceObservation(
        id=obs_id, tenant_id=tid, lease_id=lid, property_id=prop_id,
        observed_at=_utcnow(),
        balance_total=to_decimal(row.get("balance_total") or row.get("amount_owed") or row.get("balance_owed")),
        balance_0_30=to_decimal(row.get("balance_0_30")),
        balance_30_plus=to_decimal(row.get("balance_30_plus")),
        last_payment_date=to_date(row.get("last_payment_date")),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.insert_balance_observation(obs)
    await _persist_delinquency_notes(row, ctx, tid)


async def _persist_delinquency_notes(row: dict[str, Any], ctx: IngestionCtx, tenant_id: str) -> None:
    raw = str(row.get("notes") or row.get("delinquency_notes") or row.get("delinquent_notes") or "").strip()
    if not raw:
        return
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    for idx, line in enumerate(lines):
        nid = _note_id(tenant_id, ctx.doc_id, idx)
        note = Note(id=nid, content=line, entity_type="Tenant", entity_id=tenant_id,
            provenance=NoteProvenance.DATA_DERIVED, source_doc=ctx.doc_id)
        await ctx.ps.upsert_note(note)
        await _record_extracted(ctx, nid, "Note")


async def persist_lease(row: dict[str, Any], ctx: IngestionCtx) -> None:
    prop_id = await _ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    tid = _tenant_id(tname, prop_id)
    lid = _lease_id(tname, prop_id, unum)
    rent = to_decimal(row.get("monthly_rent"))

    await ctx.ps.upsert_unit(_with_hash(Unit(
        id=uid, property_id=prop_id, unit_number=unum,
        sqft=to_int(row.get("sqft")), market_rent=to_decimal(row.get("market_rent")),
        source_document_id=ctx.doc_id,
    )))  # type: ignore[arg-type]
    await _record_extracted(ctx, uid, "Unit")

    await ctx.ps.upsert_tenant(_with_hash(Tenant(
        id=tid, name=tname,
        phone=(str(row.get("phone_numbers") or row.get("phone") or "").strip() or None),
        source_document_id=ctx.doc_id,
    )))  # type: ignore[arg-type]
    await _record_extracted(ctx, tid, "Tenant")

    start = to_date(row.get("move_in_date") or row.get("start_date"))
    end = to_date(row.get("lease_expires") or row.get("end_date"))
    lease = Lease(
        id=lid, unit_id=uid, tenant_id=tid, property_id=prop_id,
        start_date=start or LEASE_START_FALLBACK, end_date=end or LEASE_END_FALLBACK,
        monthly_rent=rent, market_rent=to_decimal(row.get("market_rent")),
        deposit=to_decimal(row.get("deposit")),
        is_month_to_month=bool(row.get("is_month_to_month", False)),
        status=LeaseStatus.ACTIVE, source_document_id=ctx.doc_id,
    )
    await _reconcile_lease(ctx, _with_hash(lease))  # type: ignore[arg-type]
    await _record_extracted(ctx, lid, "Lease")


async def persist_property(row: dict[str, Any], ctx: IngestionCtx) -> None:
    await _ensure_property(row, ctx)


async def persist_maintenance(row: dict[str, Any], ctx: IngestionCtx) -> None:
    prop_id = await _ensure_property(row, ctx)
    unum = str(row.get("unit_number") or row.get("unit_id") or "main").strip()
    uid = _unit_id(prop_id, unum)
    title = str(row.get("title") or "").strip()
    rid = _maintenance_id(prop_id, unum, title)
    cat = str(row.get("category") or "general").strip().lower()
    st = str(row.get("status") or "open").strip().lower()
    pri = str(row.get("priority") or "medium").strip().lower()
    tname = str(row.get("tenant_name") or row.get("tenant_id") or "").strip()
    tid = _tenant_id(tname, prop_id) if tname else None
    vendor_name = str(row.get("vendor") or "").strip() or None
    vid = _vendor_id(vendor_name) if vendor_name else None
    scheduled = to_date(row.get("scheduled_date"))
    completed = to_date(row.get("completed_date") or row.get("completed_on"))
    resolved_at: datetime | None = None
    if completed and MAINTENANCE_STATUS_MAP.get(st, MaintenanceStatus.OPEN) == MaintenanceStatus.COMPLETED:
        resolved_at = datetime(completed.year, completed.month, completed.day, tzinfo=UTC)
    mr = MaintenanceRequest(
        id=rid, unit_id=uid, property_id=prop_id, tenant_id=tid,
        category=MAINTENANCE_CATEGORY_MAP.get(cat, TradeCategory.GENERAL),
        priority=PRIORITY_MAP.get(pri, Priority.MEDIUM),
        title=title, description=str(row.get("description") or "").strip(),
        status=MAINTENANCE_STATUS_MAP.get(st, MaintenanceStatus.OPEN),
        scheduled_date=scheduled, completed_date=completed, resolved_at=resolved_at,
        cost=to_decimal(row.get("cost")), vendor=vendor_name, vendor_id=vid,
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_maintenance_request(_with_hash(mr))  # type: ignore[arg-type]
    await _record_extracted(ctx, rid, "MaintenanceRequest")


async def persist_owner(row: dict[str, Any], ctx: IngestionCtx) -> None:
    from remi.application.core.models.enums import OwnerType
    name = str(row.get("name") or row.get("owner_name") or "").strip()
    if not name:
        return
    oid = _owner_id(name)
    raw_type = str(row.get("owner_type") or "other").strip().lower()
    otype = OwnerType(raw_type) if raw_type in {m.value for m in OwnerType} else OwnerType.OTHER
    owner = Owner(
        id=oid, name=name, owner_type=otype,
        company=str(row.get("company") or "").strip() or None,
        email=str(row.get("email") or "").strip(),
        phone=str(row.get("phone") or "").strip() or None,
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_owner(_with_hash(owner))  # type: ignore[arg-type]
    await _record_extracted(ctx, oid, "Owner")


async def persist_vendor(row: dict[str, Any], ctx: IngestionCtx) -> None:
    name = str(row.get("name") or row.get("vendor_name") or "").strip()
    if not name:
        return
    vid = _vendor_id(name)
    cat_raw = str(row.get("category") or "general").strip().lower()
    vendor = Vendor(
        id=vid, name=name,
        category=TradeCategory(cat_raw) if cat_raw in {m.value for m in TradeCategory} else TradeCategory.GENERAL,
        phone=str(row.get("phone") or "").strip() or None,
        email=str(row.get("email") or "").strip() or None,
        is_internal=bool(row.get("is_internal", False)),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_vendor(_with_hash(vendor))  # type: ignore[arg-type]
    await _record_extracted(ctx, vid, "Vendor")


async def persist_manager(row: dict[str, Any], ctx: IngestionCtx) -> None:
    raw_name = str(row.get("site_manager_name") or row.get("name") or row.get("manager_name") or "").strip()
    if not raw_name:
        return
    mgr_name = manager_name_from_tag(raw_name)
    mid = _manager_id(mgr_name)
    tag = str(row.get("manager_tag") or raw_name).strip()
    existing = await ctx.ps.get_manager(mid)
    base = existing or PropertyManager(id=mid, name=mgr_name)
    updates: dict[str, str | int | None] = {"manager_tag": tag, "source_document_id": ctx.doc_id}
    for field, key in (("email", "email"), ("phone", "phone"), ("company", "company"),
                       ("title", "title"), ("territory", "territory"), ("license_number", "license_number")):
        raw = str(row.get(key) or "").strip() or None
        if raw is not None:
            updates[field] = raw
    raw_max = row.get("max_units")
    if raw_max is not None:
        with contextlib.suppress(TypeError, ValueError):
            updates["max_units"] = int(raw_max)
    manager = base.model_copy(update=updates)
    await ctx.ps.upsert_manager(_with_hash(manager))  # type: ignore[arg-type]
    await _record_extracted(ctx, mid, "PropertyManager")

    if row.get("property_address"):
        prop_row = {**row, "type": "Property"}
        addr = str(row["property_address"])
        ctx.property_manager[_property_id(property_name(addr) or addr)] = mid
        await _ensure_property(prop_row, ctx)


_Persister = Callable[["dict[str, Any]", IngestionCtx], Any]

ROW_PERSISTERS: dict[str, _Persister] = {
    "Unit": persist_unit,
    "Tenant": persist_tenant,
    "BalanceObservation": persist_tenant,
    "Lease": persist_lease,
    "Property": persist_property,
    "MaintenanceRequest": persist_maintenance,
    "Owner": persist_owner,
    "Vendor": persist_vendor,
    "PropertyManager": persist_manager,
}


# ---------------------------------------------------------------------------
# Tool registration — called once per upload
# ---------------------------------------------------------------------------

_MANAGER_SCOPES = frozenset({"manager_portfolio", "single_property", "single_unit"})


def register_ingestion_tools(
    registry: ToolRegistry, *, ps: PropertyStore, doc_id: str,
    platform: str, result: IngestionResult,
    all_rows: list[dict[str, Any]], upload_manager_hint: str | None = None,
) -> None:
    _ctx_cell: list[IngestionCtx | None] = [None]

    def _ctx() -> IngestionCtx:
        c = _ctx_cell[0]
        if c is None:
            raise RuntimeError("initialize tool must run before other ingestion tools")
        return c

    async def _initialize_tool(args: dict[str, Any]) -> dict[str, Any]:
        raw_rt = str(args.get("report_type") or "unknown").strip()
        scope = str(args.get("scope") or "unknown").strip()
        manager_name: str | None = args.get("manager_name") or None
        try:
            rt = ReportType(raw_rt)
        except ValueError:
            rt = ReportType.UNKNOWN
        ctx = IngestionCtx(
            platform=platform, report_type=rt, doc_id=doc_id, namespace="ingestion",
            ps=ps, manager_resolver=ManagerResolver(ps), result=result,
        )
        _ctx_cell[0] = ctx
        result.report_type = rt
        candidate = manager_name or upload_manager_hint
        resolved_manager_id: str | None = None
        resolved_manager_name: str | None = None
        created_new = False
        if candidate and scope in _MANAGER_SCOPES:
            resolver = ManagerResolver(ps)
            resolution = await resolver.ensure_manager(candidate)
            resolved_manager_id = resolution.manager_id
            resolved_manager_name = resolution.manager_name
            created_new = resolution.created_new
            ctx.upload_manager_id = resolution.manager_id
            _log.info("ingestion_manager_resolved", manager_id=resolution.manager_id,
                manager_name=resolution.manager_name,
                source="llm_extract" if manager_name else "upload_hint",
                created_new=resolution.created_new, scope=scope, report_type=rt.value)
        return {"manager_id": resolved_manager_id, "manager_name": resolved_manager_name,
                "report_type": rt.value, "created_new": created_new}

    async def _merge_maps_tool(args: dict[str, Any]) -> dict[str, Any]:
        base: dict[str, str] = args.get("base_map") or {}
        override: dict[str, str] = args.get("override_map") or {}
        merged = {**base, **override}
        _log.info("merge_maps", base_keys=len(base), override_keys=len(override), merged_keys=len(merged))
        return {"column_map": merged}

    async def _apply_column_map_tool(args: dict[str, Any]) -> dict[str, Any]:
        column_map: dict[str, str] = args.get("column_map", {})
        entity_type: str = args.get("entity_type", "")
        section_header: str | None = args.get("section_header_column")
        if not column_map or not entity_type:
            _log.warning("apply_column_map_empty", has_map=bool(column_map), entity_type=entity_type)
            return {"rows": [], "skipped": 0}
        mapped = apply_column_map(all_rows, column_map, entity_type, section_header_column=section_header)
        return {"rows": mapped, "total": len(all_rows), "mapped": len(mapped)}

    async def _validate_rows_tool(args: dict[str, Any]) -> dict[str, Any]:
        rows = args.get("rows", [])
        if not isinstance(rows, list):
            rows = []
        accepted = validate_rows(rows, result)
        return {"accepted": accepted, "total": len(rows),
                "accepted_count": len(accepted), "rejected_count": result.rows_rejected}

    async def _persist_row_tool(args: dict[str, Any]) -> dict[str, str]:
        ctx = _ctx()
        entity_type = args.get("type", "")
        persister = ROW_PERSISTERS.get(entity_type)
        if persister is None:
            result.observation_rows.append(args)
            result.rows_skipped += 1
            return {"status": "skipped", "type": entity_type}
        try:
            await persister(args, ctx)
            return {"status": "ok", "type": entity_type}
        except Exception as exc:
            _log.warning("row_persist_error", entity_type=entity_type, error=str(exc), exc_info=True)
            result.persist_errors.append(RowWarning(
                row_index=0, row_type=entity_type, field="", issue="persistence failed",
                raw_value=str(args)[:200],
            ))
            result.rows_rejected += 1
            raise

    registry.register("initialize", _initialize_tool, ToolDefinition(
        name="initialize", description="Create ingestion context, resolve manager, stamp report type"))
    registry.register("merge_maps", _merge_maps_tool, ToolDefinition(
        name="merge_maps", description="Merge extract and inspect column maps; inspect entries win"))
    registry.register("apply_column_map", _apply_column_map_tool, ToolDefinition(
        name="apply_column_map", description="Map document columns to entity fields"))
    registry.register("validate_rows", _validate_rows_tool, ToolDefinition(
        name="validate_rows", description="Validate mapped rows for ingestion"))
    registry.register("persist_row", _persist_row_tool, ToolDefinition(
        name="persist_row", description="Persist a single validated row"))
