"""Per-entity-type persist handlers for ingestion rows.

Ingestion is now *reconciling*, not replacing:
- Units accumulate physical facts; occupancy is never stored on Unit.
- Leases accumulate; when a new tenant is seen on a unit the previous
  active lease is marked TERMINATED before the new one is upserted.
- BalanceObservations are always inserted (never updated); the full
  history of what each delinquency report said is preserved.
- Tenant stores identity and eviction status only; balances live in
  BalanceObservation.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel as _BaseModel

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
    PropertyManager,
    Tenant,
    TenantStatus,
    TradeCategory,
    Unit,
    Vendor,
)
from remi.application.services.ingestion.context import (
    IngestionCtx,
    ensure_property,
    record_extracted,
)
from remi.application.services.ingestion.resolver import (
    LEASE_END_FALLBACK,
    LEASE_START_FALLBACK,
    MAINTENANCE_CATEGORY_MAP,
    MAINTENANCE_STATUS_MAP,
    PRIORITY_MAP,
    TENANT_STATUS_MAP,
    property_name,
    to_date,
    to_decimal,
    to_int,
)
from remi.types.identity import (
    balance_observation_id as _bal_obs_id,
)
from remi.types.identity import (
    content_hash as _content_hash,
)
from remi.types.identity import (
    lease_id as _lease_id,
)
from remi.types.identity import (
    maintenance_id as _maintenance_id,
)
from remi.types.identity import (
    manager_id as _manager_id,
)
from remi.types.identity import (
    note_id as _note_id,
)
from remi.types.identity import (
    owner_id as _owner_id,
)
from remi.types.identity import (
    property_id as _property_id,
)
from remi.types.identity import (
    tenant_id as _tenant_id,
)
from remi.types.identity import (
    unit_id as _unit_id,
)
from remi.types.identity import (
    vendor_id as _vendor_id,
)


def _with_hash(entity: _BaseModel) -> _BaseModel:
    """Return a copy of *entity* with its content_hash field populated."""
    h = _content_hash(entity.model_dump(mode="json"))
    return entity.model_copy(update={"content_hash": h})


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _reconcile_lease(
    ctx: IngestionCtx,
    new_lease: Lease,
) -> None:
    """Upsert *new_lease*, terminating any prior active lease on the same unit
    that belonged to a different tenant.

    This is the core of temporal lease tracking: old leases are never deleted,
    just transitioned to TERMINATED so history is preserved.
    """
    existing_active = await ctx.ps.list_leases(unit_id=new_lease.unit_id, status=LeaseStatus.ACTIVE)
    for existing in existing_active:
        if existing.id == new_lease.id:
            continue
        if existing.tenant_id != new_lease.tenant_id:
            await ctx.ps.upsert_lease(
                existing.model_copy(update={"status": LeaseStatus.TERMINATED})
            )

    # Set temporal tracking fields
    prior = await ctx.ps.get_lease(new_lease.id)
    now = _utcnow()
    update: dict[str, object] = {"last_confirmed_at": now}
    if prior is None:
        update["first_seen_at"] = now

    await ctx.ps.upsert_lease(
        new_lease.model_copy(update=update)  # type: ignore[arg-type]
    )


async def persist_unit(row: dict[str, Any], ctx: IngestionCtx) -> None:
    """Persist physical unit facts from a rent roll or similar report."""
    prop_id = await ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)

    unit = Unit(
        id=uid,
        property_id=prop_id,
        unit_number=unum,
        bedrooms=to_int(row.get("bedrooms")),
        bathrooms=(float(row["bathrooms"]) if row.get("bathrooms") is not None else None),
        sqft=to_int(row.get("sqft")),
        market_rent=to_decimal(row.get("market_rent")),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_unit(_with_hash(unit))  # type: ignore[arg-type]
    await record_extracted(ctx, uid, "Unit")

    # If the rent roll row has tenant/lease data, reconcile the lease
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    rent = to_decimal(row.get("monthly_rent") or row.get("current_rent"))
    if tname and rent > 0:
        tid = _tenant_id(tname, prop_id)
        lid = _lease_id(tname, prop_id, unum)
        tenant = Tenant(
            id=tid,
            name=tname,
            phone=(str(row.get("phone_numbers") or row.get("phone") or "").strip() or None),
            source_document_id=ctx.doc_id,
        )
        await ctx.ps.upsert_tenant(_with_hash(tenant))  # type: ignore[arg-type]
        await record_extracted(ctx, tid, "Tenant")

        start = to_date(row.get("move_in_date") or row.get("start_date"))
        end = to_date(row.get("lease_expires") or row.get("end_date"))
        lease = Lease(
            id=lid,
            unit_id=uid,
            tenant_id=tid,
            property_id=prop_id,
            start_date=start or LEASE_START_FALLBACK,
            end_date=end or LEASE_END_FALLBACK,
            monthly_rent=rent,
            market_rent=to_decimal(row.get("market_rent")),
            deposit=to_decimal(row.get("deposit")),
            is_month_to_month=bool(row.get("is_month_to_month", False)),
            status=LeaseStatus.ACTIVE,
            source_document_id=ctx.doc_id,
        )
        await _reconcile_lease(ctx, _with_hash(lease))  # type: ignore[arg-type]
        await record_extracted(ctx, lid, "Lease")


async def persist_tenant(row: dict[str, Any], ctx: IngestionCtx) -> None:
    """Delinquency rows: upsert identity, confirm lease, insert balance observation."""
    prop_id = await ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    tid = _tenant_id(tname, prop_id)
    lid = _lease_id(tname, prop_id, unum)

    await ctx.ps.upsert_unit(
        _with_hash(
            Unit(
                id=uid,
                property_id=prop_id,
                unit_number=unum,
                source_document_id=ctx.doc_id,
            )
        )
    )  # type: ignore[arg-type]
    await record_extracted(ctx, uid, "Unit")

    raw_st = row.get("tenant_status") or row.get("status") or "current"
    tenant = Tenant(
        id=tid,
        name=tname,
        status=TENANT_STATUS_MAP.get(str(raw_st).strip().lower(), TenantStatus.CURRENT),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_tenant(_with_hash(tenant))  # type: ignore[arg-type]
    await record_extracted(ctx, tid, "Tenant")

    lease = Lease(
        id=lid,
        unit_id=uid,
        tenant_id=tid,
        property_id=prop_id,
        start_date=LEASE_START_FALLBACK,
        end_date=LEASE_END_FALLBACK,
        monthly_rent=to_decimal(row.get("monthly_rent")),
        status=LeaseStatus.ACTIVE,
        source_document_id=ctx.doc_id,
    )
    await _reconcile_lease(ctx, _with_hash(lease))  # type: ignore[arg-type]
    await record_extracted(ctx, lid, "Lease")

    obs_id = _bal_obs_id(tid, ctx.doc_id)
    obs = BalanceObservation(
        id=obs_id,
        tenant_id=tid,
        lease_id=lid,
        property_id=prop_id,
        observed_at=_utcnow(),
        balance_total=to_decimal(
            row.get("balance_total") or row.get("amount_owed") or row.get("balance_owed")
        ),
        balance_0_30=to_decimal(row.get("balance_0_30")),
        balance_30_plus=to_decimal(row.get("balance_30_plus")),
        last_payment_date=to_date(row.get("last_payment_date")),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.insert_balance_observation(obs)

    await _persist_delinquency_notes(row, ctx, tid)


async def _persist_delinquency_notes(
    row: dict[str, Any],
    ctx: IngestionCtx,
    tenant_id: str,
) -> None:
    raw = str(
        row.get("notes") or row.get("delinquency_notes") or row.get("delinquent_notes") or ""
    ).strip()
    if not raw:
        return

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    for idx, line in enumerate(lines):
        nid = _note_id(tenant_id, ctx.doc_id, idx)
        note = Note(
            id=nid,
            content=line,
            entity_type="Tenant",
            entity_id=tenant_id,
            provenance=NoteProvenance.DATA_DERIVED,
            source_doc=ctx.doc_id,
        )
        await ctx.ps.upsert_note(note)
        await record_extracted(ctx, nid, "Note")


async def persist_lease(row: dict[str, Any], ctx: IngestionCtx) -> None:
    """Persist a lease from a lease-expiration or similar report."""
    prop_id = await ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    tid = _tenant_id(tname, prop_id)
    lid = _lease_id(tname, prop_id, unum)

    rent = to_decimal(row.get("monthly_rent"))

    await ctx.ps.upsert_unit(
        _with_hash(
            Unit(
                id=uid,
                property_id=prop_id,
                unit_number=unum,
                sqft=to_int(row.get("sqft")),
                market_rent=to_decimal(row.get("market_rent")),
                source_document_id=ctx.doc_id,
            )
        )
    )  # type: ignore[arg-type]
    await record_extracted(ctx, uid, "Unit")

    await ctx.ps.upsert_tenant(
        _with_hash(
            Tenant(
                id=tid,
                name=tname,
                phone=(str(row.get("phone_numbers") or row.get("phone") or "").strip() or None),
                source_document_id=ctx.doc_id,
            )
        )
    )  # type: ignore[arg-type]
    await record_extracted(ctx, tid, "Tenant")

    start = to_date(row.get("move_in_date") or row.get("start_date"))
    end = to_date(row.get("lease_expires") or row.get("end_date"))
    lease = Lease(
        id=lid,
        unit_id=uid,
        tenant_id=tid,
        property_id=prop_id,
        start_date=start or LEASE_START_FALLBACK,
        end_date=end or LEASE_END_FALLBACK,
        monthly_rent=rent,
        market_rent=to_decimal(row.get("market_rent")),
        deposit=to_decimal(row.get("deposit")),
        is_month_to_month=bool(row.get("is_month_to_month", False)),
        status=LeaseStatus.ACTIVE,
        source_document_id=ctx.doc_id,
    )
    await _reconcile_lease(ctx, _with_hash(lease))  # type: ignore[arg-type]
    await record_extracted(ctx, lid, "Lease")


async def persist_property(row: dict[str, Any], ctx: IngestionCtx) -> None:
    await ensure_property(row, ctx)


async def persist_maintenance(
    row: dict[str, Any],
    ctx: IngestionCtx,
) -> None:
    prop_id = await ensure_property(row, ctx)
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
        id=rid,
        unit_id=uid,
        property_id=prop_id,
        tenant_id=tid,
        category=MAINTENANCE_CATEGORY_MAP.get(cat, TradeCategory.GENERAL),
        priority=PRIORITY_MAP.get(pri, Priority.MEDIUM),
        title=title,
        description=str(row.get("description") or "").strip(),
        status=MAINTENANCE_STATUS_MAP.get(st, MaintenanceStatus.OPEN),
        scheduled_date=scheduled,
        completed_date=completed,
        resolved_at=resolved_at,
        cost=to_decimal(row.get("cost")),
        vendor=vendor_name,
        vendor_id=vid,
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_maintenance_request(_with_hash(mr))  # type: ignore[arg-type]
    await record_extracted(ctx, rid, "MaintenanceRequest")


async def persist_owner(row: dict[str, Any], ctx: IngestionCtx) -> None:
    from remi.application.core.models.enums import OwnerType

    name = str(row.get("name") or row.get("owner_name") or "").strip()
    if not name:
        return
    oid = _owner_id(name)

    raw_type = str(row.get("owner_type") or "other").strip().lower()
    otype = (
        OwnerType(raw_type)
        if raw_type in {m.value for m in OwnerType}
        else OwnerType.OTHER
    )

    owner = Owner(
        id=oid,
        name=name,
        owner_type=otype,
        company=str(row.get("company") or "").strip() or None,
        email=str(row.get("email") or "").strip(),
        phone=str(row.get("phone") or "").strip() or None,
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_owner(_with_hash(owner))  # type: ignore[arg-type]
    await record_extracted(ctx, oid, "Owner")


async def persist_vendor(row: dict[str, Any], ctx: IngestionCtx) -> None:
    name = str(row.get("name") or row.get("vendor_name") or "").strip()
    if not name:
        return
    vid = _vendor_id(name)
    cat_raw = str(row.get("category") or "general").strip().lower()
    vendor = Vendor(
        id=vid,
        name=name,
        category=(
            TradeCategory(cat_raw)
            if cat_raw in {m.value for m in TradeCategory}
            else TradeCategory.GENERAL
        ),
        phone=str(row.get("phone") or "").strip() or None,
        email=str(row.get("email") or "").strip() or None,
        is_internal=bool(row.get("is_internal", False)),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_vendor(_with_hash(vendor))  # type: ignore[arg-type]
    await record_extracted(ctx, vid, "Vendor")


async def persist_manager(row: dict[str, Any], ctx: IngestionCtx) -> None:
    """Persist a PropertyManager from a staff or property directory report.

    For property directory rows (which have both a manager name and a
    property_address), also creates/updates the Property and sets its
    manager_id — so the MANAGED_BY relationship is established.
    """
    from remi.application.core.rules import manager_name_from_tag

    # Property directories encode the manager in site_manager_name; staff
    # directories use name / manager_name. Accept all three.
    raw_name = str(
        row.get("site_manager_name") or row.get("name") or row.get("manager_name") or ""
    ).strip()
    if not raw_name:
        return

    mgr_name = manager_name_from_tag(raw_name)
    mid = _manager_id(mgr_name)
    tag = str(row.get("manager_tag") or raw_name).strip()

    existing = await ctx.ps.get_manager(mid)
    base = existing or PropertyManager(id=mid, name=mgr_name)

    updates: dict[str, str | int | None] = {
        "manager_tag": tag,
        "source_document_id": ctx.doc_id,
    }
    for field, key in (
        ("email", "email"),
        ("phone", "phone"),
        ("company", "company"),
        ("title", "title"),
        ("territory", "territory"),
        ("license_number", "license_number"),
    ):
        raw = str(row.get(key) or "").strip() or None
        if raw is not None:
            updates[field] = raw
    raw_max = row.get("max_units")
    if raw_max is not None:
        with contextlib.suppress(TypeError, ValueError):
            updates["max_units"] = int(raw_max)

    manager = base.model_copy(update=updates)
    await ctx.ps.upsert_manager(_with_hash(manager))  # type: ignore[arg-type]
    await record_extracted(ctx, mid, "PropertyManager")

    # If this row also carries a property address (property directory pattern),
    # create/update the property with this manager assigned.
    if row.get("property_address"):
        prop_row = {**row, "type": "Property"}
        addr = str(row["property_address"])
        ctx.property_manager[_property_id(property_name(addr) or addr)] = mid
        await ensure_property(prop_row, ctx)


_Persister = Callable[["dict[str, Any]", IngestionCtx], Any]

ROW_PERSISTERS: dict[str, _Persister] = {
    "Unit": persist_unit,
    "Tenant": persist_tenant,
    "BalanceObservation": persist_tenant,  # delinquency: Tenant + Lease + BalanceObservation
    "Lease": persist_lease,
    "Property": persist_property,
    "MaintenanceRequest": persist_maintenance,
    "Owner": persist_owner,
    "Vendor": persist_vendor,
    "PropertyManager": persist_manager,
}
