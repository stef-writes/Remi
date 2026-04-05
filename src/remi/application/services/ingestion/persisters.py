"""Per-entity-type persist handlers for ingestion rows."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from remi.application.core.models import (
    Lease,
    LeaseStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
    OccupancyStatus,
    Owner,
    Priority,
    PropertyManager,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
    Vendor,
    VendorCategory,
)
from remi.application.services.ingestion.context import (
    IngestionCtx,
    ensure_property,
    link,
    merge_kb,
)
from remi.application.services.ingestion.resolver import (
    LEASE_END_FALLBACK,
    LEASE_START_FALLBACK,
    MAINTENANCE_CATEGORY_MAP,
    MAINTENANCE_STATUS_MAP,
    OCCUPANCY_MAP,
    PRIORITY_MAP,
    TENANT_STATUS_MAP,
    UNIT_STATUS_FROM_OCCUPANCY,
    to_date,
    to_decimal,
    to_int,
)
from remi.types.text import slugify


async def persist_unit(row: dict[str, Any], ctx: IngestionCtx) -> None:
    prop_id = await ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = slugify(f"unit:{prop_id}:{unum}")

    occ_str = str(row.get("occupancy_status", "")).lower().replace("-", "_")
    occ = OCCUPANCY_MAP.get(occ_str)
    status = UNIT_STATUS_FROM_OCCUPANCY.get(occ, UnitStatus.VACANT) if occ else UnitStatus.VACANT

    unit = Unit(
        id=uid,
        property_id=prop_id,
        unit_number=unum,
        status=status,
        occupancy_status=occ,
        bedrooms=to_int(row.get("bedrooms")),
        bathrooms=(float(row["bathrooms"]) if row.get("bathrooms") is not None else None),
        sqft=to_int(row.get("sqft")),
        market_rent=to_decimal(row.get("market_rent")),
        current_rent=to_decimal(row.get("monthly_rent") or row.get("current_rent")),
        days_vacant=to_int(row.get("days_vacant")),
        listed_on_website=bool(row.get("posted_website", False)),
        listed_on_internet=bool(row.get("posted_internet", False)),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_unit(unit)

    kb: dict[str, str | int | float | bool | None] = {
        "property_id": prop_id,
        "unit_number": unum,
        "status": status,
        "source_doc": ctx.doc_id,
    }
    if occ is not None:
        kb["occupancy_status"] = occ
    if unit.bedrooms is not None:
        kb["bedrooms"] = unit.bedrooms
    if unit.bathrooms is not None:
        kb["bathrooms"] = unit.bathrooms
    if unit.sqft is not None:
        kb["sqft"] = unit.sqft
    if unit.days_vacant is not None:
        kb["days_vacant"] = unit.days_vacant
    kb["listed_on_website"] = unit.listed_on_website
    kb["listed_on_internet"] = unit.listed_on_internet

    await merge_kb(ctx, uid, f"{ctx.platform}_unit", kb)
    await link(ctx, uid, prop_id, "belongs_to")
    ctx.result.entities_created += 1
    ctx.result.relationships_created += 1


async def persist_tenant(row: dict[str, Any], ctx: IngestionCtx) -> None:
    """Delinquency rows: each row implies Unit + Tenant + Lease."""
    prop_id = await ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = slugify(f"unit:{prop_id}:{unum}")
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    tid = slugify(f"tenant:{tname}:{prop_id}")
    lid = slugify(f"lease:{tname}:{prop_id}:{unum}")

    await ctx.ps.upsert_unit(
        Unit(
            id=uid,
            property_id=prop_id,
            unit_number=unum,
            status=UnitStatus.OCCUPIED,
            occupancy_status=OccupancyStatus.OCCUPIED,
            current_rent=to_decimal(row.get("monthly_rent")),
            source_document_id=ctx.doc_id,
        )
    )
    await merge_kb(
        ctx,
        uid,
        f"{ctx.platform}_unit",
        {
            "property_id": prop_id,
            "unit_number": unum,
            "status": UnitStatus.OCCUPIED,
            "source_doc": ctx.doc_id,
        },
    )
    await link(ctx, uid, prop_id, "belongs_to")
    ctx.result.entities_created += 1
    ctx.result.relationships_created += 1

    raw_st = row.get("tenant_status") or row.get("status") or "current"
    tenant = Tenant(
        id=tid,
        name=tname,
        status=TENANT_STATUS_MAP.get(str(raw_st).strip().lower(), TenantStatus.CURRENT),
        balance_owed=to_decimal(row.get("amount_owed") or row.get("balance_owed")),
        balance_0_30=to_decimal(row.get("balance_0_30")),
        balance_30_plus=to_decimal(row.get("balance_30_plus")),
        last_payment_date=to_date(row.get("last_payment_date")),
        tags=[t.strip() for t in str(row.get("tags") or "").split(",") if t.strip()],
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_tenant(tenant)

    kb_type = (
        f"{ctx.platform}_delinquent_tenant"
        if ctx.report_type == "delinquency"
        else f"{ctx.platform}_tenant"
    )
    tp: dict[str, str | float | bool | None] = {
        "name": tname,
        "status": tenant.status,
        "balance_owed": str(tenant.balance_owed),
        "balance_0_30": str(tenant.balance_0_30),
        "balance_30_plus": str(tenant.balance_30_plus),
        "source_doc": ctx.doc_id,
    }
    if tenant.last_payment_date:
        tp["last_payment_date"] = tenant.last_payment_date.isoformat()
    if tenant.tags:
        tp["tags"] = ",".join(tenant.tags)
    if tenant.phone:
        tp["phone"] = tenant.phone
    await merge_kb(ctx, tid, kb_type, tp)
    ctx.result.entities_created += 1

    await ctx.ps.upsert_lease(
        Lease(
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
    )
    await merge_kb(
        ctx,
        lid,
        f"{ctx.platform}_lease",
        {
            "unit_id": uid,
            "tenant_id": tid,
            "property_id": prop_id,
            "monthly_rent": str(to_decimal(row.get("monthly_rent"))),
            "status": LeaseStatus.ACTIVE,
            "source_doc": ctx.doc_id,
        },
    )
    await link(ctx, tid, uid, "leases")
    await link(ctx, tid, prop_id, "owes_balance_at")
    ctx.result.entities_created += 1
    ctx.result.relationships_created += 2

    await _persist_delinquency_notes(row, ctx, tid)


async def _persist_delinquency_notes(
    row: dict[str, Any],
    ctx: IngestionCtx,
    tenant_id: str,
) -> None:
    """Parse the notes/delinquency_notes field into KG Note entities.

    Delinquency reports carry a freeform notes column that contains the
    collections communication log — payment promises, demand letters,
    phone call summaries.  Each non-empty line becomes a Note entity
    linked to the tenant via HAS_NOTE.
    """
    raw = str(
        row.get("notes") or row.get("delinquency_notes") or row.get("delinquent_notes") or ""
    ).strip()
    if not raw:
        return

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    for idx, line in enumerate(lines):
        nid = slugify(f"note:{tenant_id}:{ctx.doc_id}:{idx}")
        await merge_kb(
            ctx,
            nid,
            "delinquency_note",
            {
                "content": line,
                "entity_type": "Tenant",
                "entity_id": tenant_id,
                "provenance": "data_derived",
                "source_doc": ctx.doc_id,
            },
        )
        await link(ctx, tenant_id, nid, "has_note")
        ctx.result.entities_created += 1
        ctx.result.relationships_created += 1


async def persist_lease(row: dict[str, Any], ctx: IngestionCtx) -> None:
    prop_id = await ensure_property(row, ctx)
    unum = str(row.get("unit_number") or "main").strip()
    uid = slugify(f"unit:{prop_id}:{unum}")
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    tid = slugify(f"tenant:{tname}:{prop_id}")
    lid = slugify(f"lease:{tname}:{prop_id}:{unum}")

    rent = to_decimal(row.get("monthly_rent"))
    active = rent > 0 and bool(tname)

    await ctx.ps.upsert_unit(
        Unit(
            id=uid,
            property_id=prop_id,
            unit_number=unum,
            status=UnitStatus.OCCUPIED if active else UnitStatus.VACANT,
            occupancy_status=(OccupancyStatus.OCCUPIED if active else None),
            sqft=to_int(row.get("sqft")),
            market_rent=to_decimal(row.get("market_rent")),
            current_rent=rent,
            source_document_id=ctx.doc_id,
        )
    )
    await merge_kb(
        ctx,
        uid,
        f"{ctx.platform}_unit",
        {
            "property_id": prop_id,
            "unit_number": unum,
            "status": UnitStatus.OCCUPIED if active else UnitStatus.VACANT,
            "source_doc": ctx.doc_id,
        },
    )
    await link(ctx, uid, prop_id, "belongs_to")
    ctx.result.entities_created += 1
    ctx.result.relationships_created += 1

    await ctx.ps.upsert_tenant(
        Tenant(
            id=tid,
            name=tname,
            status=TenantStatus.CURRENT,
            phone=(str(row.get("phone_numbers") or row.get("phone") or "").strip() or None),
            source_document_id=ctx.doc_id,
        )
    )
    await merge_kb(
        ctx,
        tid,
        f"{ctx.platform}_tenant",
        {
            "name": tname,
            "status": TenantStatus.CURRENT,
            "source_doc": ctx.doc_id,
        },
    )
    ctx.result.entities_created += 1

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
    await ctx.ps.upsert_lease(lease)

    lp: dict[str, str | int | float | bool | None] = {
        "unit_id": uid,
        "tenant_id": tid,
        "property_id": prop_id,
        "monthly_rent": str(rent),
        "is_month_to_month": str(lease.is_month_to_month),
        "status": LeaseStatus.ACTIVE,
        "source_doc": ctx.doc_id,
    }
    if start:
        lp["start_date"] = start.isoformat()
    if end:
        lp["end_date"] = end.isoformat()
    await merge_kb(ctx, lid, f"{ctx.platform}_lease", lp)
    await link(ctx, tid, uid, "leases")
    await link(ctx, tid, prop_id, "owes_balance_at")
    ctx.result.entities_created += 1
    ctx.result.relationships_created += 2


async def persist_property(row: dict[str, Any], ctx: IngestionCtx) -> None:
    await ensure_property(row, ctx)


async def persist_maintenance(
    row: dict[str, Any],
    ctx: IngestionCtx,
) -> None:
    prop_id = await ensure_property(row, ctx)
    unum = str(row.get("unit_number") or row.get("unit_id") or "main").strip()
    uid = slugify(f"unit:{prop_id}:{unum}")
    title = str(row.get("title") or "").strip()
    rid = slugify(f"maint:{prop_id}:{unum}:{title or 'request'}")

    cat = str(row.get("category") or "general").strip().lower()
    st = str(row.get("status") or "open").strip().lower()
    pri = str(row.get("priority") or "medium").strip().lower()
    tname = str(row.get("tenant_name") or row.get("tenant_id") or "").strip()
    tid = slugify(f"tenant:{tname}:{prop_id}") if tname else None

    mr = MaintenanceRequest(
        id=rid,
        unit_id=uid,
        property_id=prop_id,
        tenant_id=tid,
        category=MAINTENANCE_CATEGORY_MAP.get(cat, MaintenanceCategory.GENERAL),
        priority=PRIORITY_MAP.get(pri, Priority.MEDIUM),
        title=title,
        description=str(row.get("description") or "").strip(),
        status=MAINTENANCE_STATUS_MAP.get(st, MaintenanceStatus.OPEN),
        cost=to_decimal(row.get("cost")),
        vendor=str(row.get("vendor") or "").strip() or None,
    )
    await ctx.ps.upsert_maintenance_request(mr)

    mp: dict[str, str | int | float | bool | None] = {
        "unit_id": uid,
        "property_id": prop_id,
        "category": mr.category,
        "priority": mr.priority,
        "status": mr.status,
        "source_doc": ctx.doc_id,
    }
    if title:
        mp["title"] = title
    if tid:
        mp["tenant_id"] = tid
    if mr.vendor:
        mp["vendor"] = mr.vendor
    if mr.cost:
        mp["cost"] = str(mr.cost)

    await merge_kb(ctx, rid, f"{ctx.platform}_maintenance_request", mp)
    await link(ctx, rid, uid, "affects")
    ctx.result.entities_created += 1
    ctx.result.relationships_created += 1


async def persist_owner(row: dict[str, Any], ctx: IngestionCtx) -> None:
    name = str(row.get("name") or row.get("owner_name") or "").strip()
    if not name:
        return
    oid = slugify(f"owner:{name}")
    owner = Owner(
        id=oid,
        name=name,
        entity_type_label=str(row.get("entity_type_label") or "").strip(),
        email=str(row.get("email") or "").strip(),
        phone=str(row.get("phone") or "").strip() or None,
    )
    await ctx.ps.upsert_owner(owner)
    await merge_kb(
        ctx,
        oid,
        f"{ctx.platform}_owner",
        {
            "name": name,
            "source_doc": ctx.doc_id,
        },
    )
    ctx.result.entities_created += 1


async def persist_vendor(row: dict[str, Any], ctx: IngestionCtx) -> None:
    name = str(row.get("name") or row.get("vendor_name") or "").strip()
    if not name:
        return
    vid = slugify(f"vendor:{name}")
    cat_raw = str(row.get("category") or "general").strip().lower()
    vendor = Vendor(
        id=vid,
        name=name,
        category=(
            VendorCategory(cat_raw)
            if cat_raw in VendorCategory.__members__.values()
            else VendorCategory.GENERAL
        ),
        phone=str(row.get("phone") or "").strip() or None,
        email=str(row.get("email") or "").strip() or None,
        is_internal=bool(row.get("is_internal", False)),
    )
    await ctx.ps.upsert_vendor(vendor)
    await merge_kb(
        ctx,
        vid,
        f"{ctx.platform}_vendor",
        {
            "name": name,
            "category": vendor.category,
            "is_internal": vendor.is_internal,
            "source_doc": ctx.doc_id,
        },
    )
    ctx.result.entities_created += 1


async def persist_manager(row: dict[str, Any], ctx: IngestionCtx) -> None:
    """Persist a PropertyManager row from a staff/directory report.

    Accepts fields: name, email, phone, company, manager_tag, title,
    territory, max_units, license_number. Skips rows with no name.
    Uses the ManagerResolver so that name deduplication and portfolio
    creation follow the same path as tag-inferred managers.
    """
    from remi.application.core.rules import manager_name_from_tag
    from remi.types.text import slugify as _slugify

    raw_name = str(row.get("name") or row.get("manager_name") or "").strip()
    if not raw_name:
        return

    mgr_name = manager_name_from_tag(raw_name)
    manager_id = _slugify(f"manager:{mgr_name}")
    tag = str(row.get("manager_tag") or raw_name).strip()

    existing = await ctx.ps.get_manager(manager_id)
    base = existing or PropertyManager(id=manager_id, name=mgr_name)

    updates: dict[str, str | int | None] = {"manager_tag": tag}
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
    await ctx.ps.upsert_manager(manager)

    kb_props: dict[str, str | int | float | bool | None] = {
        "name": mgr_name,
        "manager_tag": tag,
        "source_doc": ctx.doc_id,
    }
    if manager.email:
        kb_props["email"] = manager.email
    if manager.company:
        kb_props["company"] = manager.company
    await merge_kb(ctx, manager_id, f"{ctx.platform}_manager", kb_props)
    ctx.result.entities_created += 1


_Persister = Callable[["dict[str, Any]", IngestionCtx], Any]

ROW_PERSISTERS: dict[str, _Persister] = {
    "Unit": persist_unit,
    "Tenant": persist_tenant,
    "Lease": persist_lease,
    "Property": persist_property,
    "MaintenanceRequest": persist_maintenance,
    "Owner": persist_owner,
    "Vendor": persist_vendor,
    "PropertyManager": persist_manager,
}
