"""Ingestion operations — core pipeline logic with zero agent-kernel dependencies.

Owns the ingestion context, manager resolution, column mapping, row validation,
entity persisters, and the deterministic pipeline entry point.  Both the
rules-first path (``run_deterministic_pipeline``) and the YAML workflow tools
(``tools.py``) call the same functions here.
"""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog
from pydantic import BaseModel as _BaseModel

from remi.application.core.models import (
    BalanceObservation,
    Lease,
    LeaseStatus,
    MaintenanceRequest,
    MaintenanceStatus,
    Note,
    NoteProvenance,
    OccupancyStatus,
    Owner,
    Priority,
    Property,
    PropertyManager,
    PropertyStatus,
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
    LEASE_END_FALLBACK,
    LEASE_START_FALLBACK,
    MAINTENANCE_CATEGORY_MAP,
    MAINTENANCE_STATUS_MAP,
    PERSISTABLE_TYPES,
    PRIORITY_MAP,
    REPORT_CAN_CREATE,
    REPORT_FIELD_AUTHORITY,
    TENANT_STATUS_MAP,
    LeaseTagFields,
    is_inactive_property,
    is_junk_property,
    is_manager_tag,
    is_section_header,
    is_summary_row,
    normalize_address,
    parse_address,
    parse_lease_tags,
    property_name,
    split_bd_ba,
    to_date,
    to_decimal,
    to_decimal_or_none,
    to_int,
    validate_row_plausibility,
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

_log = structlog.get_logger(__name__)

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
                    manager_id=mgr.id,
                    manager_name=mgr.name,
                    alias_matched=True,
                    alias_from=tag,
                    alias_to=mgr.name,
                )
                self._set_cache(tag, resolution)
                return resolution

        if tag_norm:
            prefix_matches = [
                mgr for mgr in existing_managers
                if normalize_entity_name(mgr.name).startswith(tag_norm + " ")
            ]
            if len(prefix_matches) == 1:
                mgr = prefix_matches[0]
                _log.info(
                    "manager_prefix_matched",
                    tag=tag, tag_norm=tag_norm,
                    matched_name=mgr.name, matched_id=mgr.id,
                )
                resolution = ManagerResolution(
                    manager_id=mgr.id,
                    manager_name=mgr.name,
                    alias_matched=True,
                    alias_from=tag,
                    alias_to=mgr.name,
                )
                self._set_cache(tag, resolution)
                return resolution

        # Guard: only create a new manager record when the raw tag passes the
        # lexical heuristic.  If the tag already matched in the store above,
        # we never reach this branch — so known managers are always accepted
        # regardless of whether is_manager_tag would pass.
        if not is_manager_tag(tag):
            _log.info(
                "manager_creation_skipped",
                tag=tag,
                reason="not in store and failed is_manager_tag heuristic",
            )
            return ManagerResolution(manager_id="", manager_name="")

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
        "platform",
        "report_type",
        "doc_id",
        "namespace",
        "ps",
        "manager_resolver",
        "result",
        "upload_manager_id",
        "seen_properties",
        "prop_manager_tags",
        "real_manager_tags",
        "property_manager",
        "extracted_entity_ids",
        "as_of_date",
    )

    def __init__(
        self,
        *,
        platform: str,
        report_type: ReportType,
        doc_id: str,
        namespace: str,
        ps: PropertyStore,
        manager_resolver: ManagerResolver,
        result: IngestionResult,
        upload_manager_id: str | None = None,
        as_of_date: date | None = None,
    ) -> None:
        self.platform = platform
        self.report_type = report_type
        self.doc_id = doc_id
        self.namespace = namespace
        self.ps = ps
        self.manager_resolver = manager_resolver
        self.result = result
        self.upload_manager_id = upload_manager_id
        self.as_of_date = as_of_date
        self.seen_properties: set[str] = set()
        self.prop_manager_tags: dict[str, str] = {}
        self.real_manager_tags: set[str] = set()
        self.property_manager: dict[str, str] = {}
        self.extracted_entity_ids: list[tuple[str, str]] = []


_FK_COUNTS: dict[str, int] = {
    "Property": 1,        # MANAGED_BY
    "Unit": 1,            # BELONGS_TO (property)
    "Lease": 3,           # HAS_UNIT, TENANT_ON, BELONGS_TO (property)
    "Tenant": 0,
    "BalanceObservation": 2,  # tenant, property
    "MaintenanceRequest": 2,  # unit, property
    "PropertyManager": 0,
    "Owner": 0,
    "Vendor": 0,
    "Note": 1,            # entity_id
}


async def _record_extracted(ctx: IngestionCtx, entity_id: str, entity_type: str) -> None:
    ctx.extracted_entity_ids.append((entity_id, entity_type))
    ctx.result.entities_created += 1
    ctx.result.relationships_created += _FK_COUNTS.get(entity_type, 0)


def _primary_manager_tag(raw_tag: str) -> str:
    """Return the first manager from a possibly comma-separated tag string.

    AppFolio Tags columns sometimes contain comma-separated values like
    "Mark Williams Mgmt, Brad Rembold Management".  Treating the whole
    string as one name produces garbage IDs.  We take the first non-empty
    segment — the primary manager — and discard the rest.
    """
    parts = [p.strip() for p in raw_tag.split(",") if p.strip()]
    return parts[0] if parts else raw_tag


def _pre_set_manager_tag(row: dict[str, Any], ctx: IngestionCtx, prop_id: str) -> None:
    """Populate ctx.prop_manager_tags from _manager_tag before _ensure_property runs.

    Lease expiration and delinquency reports carry the manager tag in a
    ``Tags`` column mapped to ``_manager_tag``.  Without this step,
    ``_ensure_property`` never sees the tag and the property is created
    with no manager association.

    Comma-separated tags (e.g. "Mgmt A, Mgmt B") are normalised to the
    primary (first) value via ``_primary_manager_tag``.

    Tags that don't look like manager names (e.g. "Section 8", "MTM",
    "12 Month Renewal") are silently dropped — they're lease-level labels,
    not manager identifiers.
    """
    raw = str(row.get("_manager_tag") or "").strip()
    if not raw or prop_id in ctx.prop_manager_tags:
        return
    tag = _primary_manager_tag(raw)
    if not is_manager_tag(tag):
        return
    ctx.prop_manager_tags[prop_id] = tag
    ctx.real_manager_tags.add(tag)


# Report types that are authoritative sources for Property existence.
# For all other types (delinquency, maintenance, etc.) _ensure_property will
# return None when the property is not already in the store, allowing callers
# to skip the row rather than creating a phantom property.
_PROPERTY_AUTHORITATIVE_TYPES: frozenset[ReportType] = frozenset({
    ReportType.PROPERTY_DIRECTORY,
    ReportType.RENT_ROLL,
    ReportType.LEASE_EXPIRATION,
    ReportType.UNKNOWN,  # permissive fallback for unclassified documents
})


async def _ensure_property(row: dict[str, Any], ctx: IngestionCtx) -> str | None:
    raw_addr = str(row.get("property_address", "")).strip()
    name = property_name(raw_addr) or raw_addr
    prop_id = _property_id(name)

    if prop_id in ctx.seen_properties:
        return prop_id
    ctx.seen_properties.add(prop_id)

    existing = await ctx.ps.get_property(prop_id)

    # Fuzzy fallback: different address formats for the same physical property
    # produce different deterministic IDs ("101 Main St" vs "101 Main Street").
    # Scan existing properties by normalized name to find the canonical record
    # and reuse its ID rather than creating a duplicate.
    if existing is None:
        name_norm = normalize_entity_name(name)
        for prop in await ctx.ps.list_properties():
            if normalize_entity_name(prop.name) == name_norm:
                _log.info(
                    "property_fuzzy_matched",
                    incoming_name=name,
                    canonical_name=prop.name,
                    canonical_id=prop.id,
                )
                existing = prop
                prop_id = prop.id
                # Re-check the cache with the canonical ID before continuing.
                if prop_id in ctx.seen_properties:
                    return prop_id
                ctx.seen_properties.add(prop_id)
                break

    if existing is None and ctx.report_type not in _PROPERTY_AUTHORITATIVE_TYPES:
        _log.debug(
            "property_creation_skipped",
            raw_addr=raw_addr,
            report_type=ctx.report_type.value,
            reason="report_not_authoritative",
        )
        return None
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
            ctx.result.review_items.append(
                ReviewItem(
                    kind=ReviewKind.MANAGER_INFERRED,
                    severity=ReviewSeverity.INFO,
                    message=f"Created new manager '{resolution.manager_name}' from tag '{tag}'",
                    entity_type="PropertyManager",
                    entity_id=resolution.manager_id,
                )
            )
        elif resolution.alias_matched:
            ctx.result.review_items.append(
                ReviewItem(
                    kind=ReviewKind.ENTITY_MATCH,
                    severity=ReviewSeverity.WARNING,
                    message=(
                        f"Matched tag '{resolution.alias_from}'"
                        f" to existing manager '{resolution.alias_to}'"
                    ),
                    entity_type="PropertyManager",
                    entity_id=resolution.manager_id,
                    raw_value=resolution.alias_from,
                    suggestion=resolution.alias_to,
                    options=[
                        ReviewOption(id=resolution.manager_id, label=str(resolution.alias_to)),
                        ReviewOption(
                            id="new", label=f"Create '{resolution.alias_from}' as new manager"
                        ),
                    ],
                )
            )
    elif tag:
        ctx.result.manager_tags_skipped.append(tag)

    status = PropertyStatus.INACTIVE if row.get("_inactive") else PropertyStatus.ACTIVE
    uc = to_int(row.get("_unit_count"))

    await ctx.ps.upsert_property(
        Property(
            id=prop_id,
            manager_id=mid,
            name=name,
            address=address,
            status=status,
            unit_count=uc,
            manager_tag=tag,
            source_document_id=ctx.doc_id,
        )
    )
    await _record_extracted(ctx, prop_id, "Property")
    return prop_id


# ---------------------------------------------------------------------------
# Column mapper
# ---------------------------------------------------------------------------


_NON_ENTITY_KEYS = frozenset({
    "type", "extra_fields", "_section_label",
    "site_manager_name", "_manager_tag",
})


def apply_column_map(
    rows: list[dict[str, Any]],
    column_map: dict[str, str],
    entity_type: str,
    *,
    section_header_column: str | None = None,
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

        if is_summary_row(raw_row):
            total_skipped += 1
            continue

        bd_ba = out.pop("_bd_ba", None)
        if bd_ba is not None:
            beds, baths = split_bd_ba(str(bd_ba))
            if beds is not None and "bedrooms" not in out:
                out["bedrooms"] = beds
            if baths is not None and "bathrooms" not in out:
                out["bathrooms"] = baths

        ctx_prop = out.pop("_ctx_property_address", None)
        ctx_section = out.pop("_ctx_section_label", None)
        section_prop = out.pop("_section_property", None)
        if ctx_prop:
            current_property = str(ctx_prop)
        if ctx_section:
            current_section = str(ctx_section)

        # _section_property is the denormalized property address injected
        # by the parser for every data row in grouped reports. Use it as
        # the primary fallback when the row has no explicit property_address.
        if section_prop and not current_property:
            current_property = str(section_prop)

        prop_val = str(out.get("property_address") or "").strip()
        prop_inherited = False
        if prop_val:
            if is_junk_property(prop_val):
                total_skipped += 1
                continue
            if is_inactive_property(prop_val):
                out["_inactive"] = True
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
        elif section_prop:
            raw_sp = str(section_prop)
            if is_inactive_property(raw_sp):
                out["_inactive"] = True
            normalized_sp = normalize_address(raw_sp)
            if is_junk_property(normalized_sp):
                total_skipped += 1
                continue
            out["property_address"] = normalized_sp
            current_property = normalized_sp
            prop_inherited = True
        elif current_property:
            if is_junk_property(current_property):
                total_skipped += 1
                continue
            out["property_address"] = current_property
            prop_inherited = True

        if current_section:
            out.setdefault("_section_label", current_section)

        own_fields = sum(
            1 for k, v in out.items()
            if k not in _NON_ENTITY_KEYS and v is not None
            and not (k == "property_address" and prop_inherited)
        )
        if own_fields == 0:
            total_skipped += 1
            continue

        # Plausibility check — catches cross-column mapping errors (e.g. a
        # date serial number landing in monthly_rent, or a dollar amount in
        # unit_count). Warnings don't block persistence; they're logged and
        # surfaced to callers as RowWarnings for review.
        issues = validate_row_plausibility(out)
        if issues:
            out["_plausibility_warnings"] = issues
            _log.warning(
                "row_plausibility_warning",
                entity_type=entity_type,
                issues=issues,
            )

        mapped.append(out)

    if total_skipped:
        _log.info(
            "mapper_skipped_rows",
            entity_type=entity_type,
            skipped=total_skipped,
            accepted=len(mapped),
        )

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

        # Plausibility warnings were set by apply_column_map. Emit them as
        # RowWarnings so callers can surface them in review_items / upload response.
        plaus_issues: list[str] = row.pop("_plausibility_warnings", [])
        for issue_text in plaus_issues:
            result.validation_warnings.append(
                RowWarning(
                    row_index=idx,
                    row_type=entity_type,
                    field="",
                    issue=f"plausibility: {issue_text}",
                    raw_value="",
                )
            )

        required = _PERSISTER_REQUIREMENTS.get(entity_type, frozenset())
        missing = [f for f in required if not _has_value(row, f)]
        if missing:
            for field_name in missing:
                result.validation_warnings.append(
                    RowWarning(
                        row_index=idx,
                        row_type=entity_type,
                        field=field_name,
                        issue="required source field missing",
                        raw_value="",
                    )
                )
            result.rows_rejected += 1
            _log.info(
                "row_rejected", row_index=idx, entity_type=entity_type, missing_fields=missing
            )
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


def _confidence_merge(
    existing: _BaseModel,
    updates: dict[str, object],
    report_type: ReportType,
    entity_type: str,
) -> dict[str, object]:
    """Merge updates into an existing entity using field authority rules.

    Authority fields (per REPORT_FIELD_AUTHORITY): overwrite even if the
    existing value is non-null — the report type owns these fields.
    Non-authority fields: only fill if the existing value is None, empty
    string, or zero Decimal.
    """
    from decimal import Decimal as _Dec

    authority = REPORT_FIELD_AUTHORITY.get(
        report_type.value, {},
    ).get(entity_type, frozenset())
    merged: dict[str, object] = {}
    for field, value in updates.items():
        if value is None:
            continue
        if field in authority:
            merged[field] = value
        else:
            current = getattr(existing, field, None)
            if current is None or current == "" or current == _Dec("0"):
                merged[field] = value
    return merged


async def _reconcile_lease(ctx: IngestionCtx, new_lease: Lease) -> None:
    existing_active = await ctx.ps.list_leases(unit_id=new_lease.unit_id, status=LeaseStatus.ACTIVE)
    for existing in existing_active:
        if existing.id == new_lease.id:
            continue
        if existing.tenant_id != new_lease.tenant_id:
            await ctx.ps.upsert_lease(
                existing.model_copy(update={"status": LeaseStatus.TERMINATED})
            )
    prior = await ctx.ps.get_lease(new_lease.id)
    now = _utcnow()

    if prior is not None:
        new_fields = {
            k: v for k, v in new_lease.model_dump().items()
            if k not in ("id", "unit_id", "tenant_id", "property_id",
                         "content_hash", "first_seen_at", "last_confirmed_at")
        }
        merged = _confidence_merge(prior, new_fields, ctx.report_type, "Lease")
        merged["last_confirmed_at"] = now
        merged["source_document_id"] = ctx.doc_id
        final = prior.model_copy(update=merged)
    else:
        final = new_lease.model_copy(update={
            "first_seen_at": now, "last_confirmed_at": now,
        })

    await ctx.ps.upsert_lease(_with_hash(final))  # type: ignore[arg-type]


# Maps AppFolio rent roll section headers to canonical OccupancyStatus values.
# "current" = occupied with active lease. "notice" = tenant gave notice but
# hasn't vacated. "vacant" = empty. All other values are treated as unknown.
_SECTION_TO_OCCUPANCY: dict[str, OccupancyStatus] = {
    "current": OccupancyStatus.OCCUPIED,
    "notice": OccupancyStatus.NOTICE_UNRENTED,
    "notice-rented": OccupancyStatus.NOTICE_RENTED,
    "notice-unrented": OccupancyStatus.NOTICE_UNRENTED,
    "vacant": OccupancyStatus.VACANT_UNRENTED,
    "vacant-rented": OccupancyStatus.VACANT_RENTED,
    "vacant-unrented": OccupancyStatus.VACANT_UNRENTED,
    "month-to-month": OccupancyStatus.OCCUPIED,
}


async def persist_unit(row: dict[str, Any], ctx: IngestionCtx) -> None:
    raw_mgr = str(
        row.get("site_manager_name") or row.get("manager_name") or row.get("_manager_tag") or ""
    ).strip()
    if raw_mgr:
        mgr_tag = _primary_manager_tag(raw_mgr)
        if is_manager_tag(mgr_tag):
            raw_addr = str(row.get("property_address", "")).strip()
            pid = _property_id(property_name(raw_addr) or raw_addr)
            ctx.prop_manager_tags[pid] = mgr_tag
            ctx.real_manager_tags.add(mgr_tag)

    prop_id = await _ensure_property(row, ctx)
    if prop_id is None:
        return  # rent roll is authoritative; None only occurs on misconfigured rows
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)

    proposed: dict[str, Any] = {"source_document_id": ctx.doc_id}
    beds = to_int(row.get("bedrooms"))
    if beds is not None:
        proposed["bedrooms"] = beds
    baths_raw = row.get("bathrooms")
    if baths_raw is not None:
        with contextlib.suppress(ValueError, TypeError):
            proposed["bathrooms"] = float(baths_raw)
    sqft = to_int(row.get("sqft"))
    if sqft is not None:
        proposed["sqft"] = sqft
    market = to_decimal_or_none(row.get("market_rent"))
    if market is not None:
        proposed["market_rent"] = market

    # Rent roll / vacancy section header → occupancy_status.
    # The section label ("Current", "Vacant", "Notice") is set on every row by
    # apply_column_map. When a full Lease record can't be created (no tenant
    # name or rent in the report), this is the only occupancy signal we have.
    section = str(row.get("_section_label") or "").strip().lower()
    occ_status = _SECTION_TO_OCCUPANCY.get(section)
    if occ_status is not None:
        proposed["occupancy_status"] = occ_status

    # days_vacant from the "Days Vacant" column — meaningful for vacant units.
    dv = to_int(row.get("days_vacant"))
    if dv is not None:
        proposed["days_vacant"] = dv

    existing_unit = await ctx.ps.get_unit(uid)
    if existing_unit is not None:
        merged = _confidence_merge(existing_unit, proposed, ctx.report_type, "Unit")
        merged["source_document_id"] = ctx.doc_id
        unit = existing_unit.model_copy(update=merged)
    else:
        unit = Unit(id=uid, property_id=prop_id, unit_number=unum, **proposed)

    await ctx.ps.upsert_unit(_with_hash(unit))  # type: ignore[arg-type]
    await _record_extracted(ctx, uid, "Unit")

    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    rent = to_decimal_or_none(row.get("monthly_rent") or row.get("current_rent"))
    if tname and rent is not None and rent > 0:
        tid = _tenant_id(tname, prop_id)
        lid = _lease_id(tname, prop_id, unum)
        tenant = Tenant(
            id=tid,
            name=tname,
            phone=(str(row.get("phone_numbers") or row.get("phone") or "").strip() or None),
            source_document_id=ctx.doc_id,
        )
        await ctx.ps.upsert_tenant(_with_hash(tenant))  # type: ignore[arg-type]
        await _record_extracted(ctx, tid, "Tenant")

        # Parse Tags column for lease-level signals (subsidy, MTM, notice, renewal).
        raw_tags = str(row.get("_manager_tag") or "").strip()
        tag_data: LeaseTagFields = parse_lease_tags(raw_tags)

        start = to_date(row.get("move_in_date") or row.get("start_date"))
        end = to_date(row.get("lease_expires") or row.get("end_date"))
        lease_kwargs: dict[str, Any] = {
            "id": lid,
            "unit_id": uid,
            "tenant_id": tid,
            "property_id": prop_id,
            "start_date": start or LEASE_START_FALLBACK,
            "end_date": end or LEASE_END_FALLBACK,
            "monthly_rent": rent,
            "status": LeaseStatus.ACTIVE,
            "source_document_id": ctx.doc_id,
        }
        market_lease = to_decimal_or_none(row.get("market_rent"))
        if market_lease is not None:
            lease_kwargs["market_rent"] = market_lease
        deposit = to_decimal_or_none(row.get("deposit"))
        if deposit is not None:
            lease_kwargs["deposit"] = deposit
        lease_kwargs.update(tag_data.lease_updates())
        if not lease_kwargs.get("is_month_to_month") and row.get("is_month_to_month"):
            lease_kwargs["is_month_to_month"] = True

        await _reconcile_lease(ctx, _with_hash(Lease(**lease_kwargs)))  # type: ignore[arg-type]
        await _record_extracted(ctx, lid, "Lease")


async def persist_tenant(row: dict[str, Any], ctx: IngestionCtx) -> None:
    raw_addr = str(row.get("property_address", "")).strip()
    _pid = _property_id(property_name(raw_addr) or raw_addr)
    _pre_set_manager_tag(row, ctx, _pid)

    prop_id = await _ensure_property(row, ctx)
    if prop_id is None:
        _log.debug("persist_tenant_skipped_no_property", raw_addr=raw_addr)
        return
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    tid = _tenant_id(tname, prop_id)

    # Delinquency/tenant rows enrich existing units but do not create new ones.
    # Creating units here without leases would make every such unit appear vacant,
    # inflating vacancy rates and unit counts. Occupancy comes from the rent roll.
    existing_unit = await ctx.ps.get_unit(uid)
    if existing_unit is not None:
        await ctx.ps.upsert_unit(
            _with_hash(
                existing_unit.model_copy(update={"source_document_id": ctx.doc_id})
            )
        )  # type: ignore[arg-type]

    # Parse the full Tags column for lease-level and tenant-level signals.
    # is_manager_tag() already extracted the manager; parse_lease_tags() gets
    # everything else: subsidy program, MTM, notice clause, eviction status.
    raw_tags = str(row.get("_manager_tag") or "").strip()
    tag_data: LeaseTagFields = parse_lease_tags(raw_tags)

    raw_st = row.get("tenant_status") or row.get("status") or "current"
    effective_status = (
        tag_data.tenant_status
        or TENANT_STATUS_MAP.get(str(raw_st).strip().lower(), TenantStatus.CURRENT)
    )

    tenant_updates: dict[str, object] = {
        "name": tname,
        "status": effective_status,
        "source_document_id": ctx.doc_id,
    }
    existing_tenant = await ctx.ps.get_tenant(tid)
    if existing_tenant is not None:
        merged = _confidence_merge(existing_tenant, tenant_updates, ctx.report_type, "Tenant")
        merged["source_document_id"] = ctx.doc_id
        tenant = existing_tenant.model_copy(update=merged)
    else:
        tenant = Tenant(id=tid, **tenant_updates)  # type: ignore[arg-type]

    await ctx.ps.upsert_tenant(_with_hash(tenant))  # type: ignore[arg-type]
    await _record_extracted(ctx, tid, "Tenant")

    obs_id = _bal_obs_id(tid, ctx.doc_id)
    observed_at = (
        datetime.combine(ctx.as_of_date, datetime.min.time(), tzinfo=UTC)
        if ctx.as_of_date is not None
        else _utcnow()
    )
    obs = BalanceObservation(
        id=obs_id,
        tenant_id=tid,
        lease_id=None,
        property_id=prop_id,
        observed_at=observed_at,
        balance_total=to_decimal(
            row.get("balance_total") or row.get("amount_owed") or row.get("balance_owed")
        ),
        balance_0_30=to_decimal(row.get("balance_0_30")),
        balance_30_plus=to_decimal(row.get("balance_30_plus")),
        subsidy_balance=to_decimal(row.get("_delinquent_subsidy")),
        last_payment_date=to_date(row.get("last_payment_date")),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.insert_balance_observation(obs)
    await _persist_delinquency_notes(row, ctx, tid)

    # Graph enrichment: walk Tenant → TENANT_ON → Lease and propagate any
    # tag-derived fields (subsidy_program, notice_days, is_month_to_month,
    # renewal_status). Delinquency reports are often the only source of these
    # signals — they must not be discarded just because this row's entity type
    # is BalanceObservation.
    lease_updates = tag_data.lease_updates()
    if lease_updates:
        existing_leases = await ctx.ps.list_leases(
            tenant_id=tid, property_id=prop_id, status=LeaseStatus.ACTIVE
        )
        for existing_lease in existing_leases:
            merged = _confidence_merge(
                existing_lease, lease_updates, ctx.report_type, "Lease",
            )
            if merged:
                enriched = _with_hash(existing_lease.model_copy(update=merged))
                await ctx.ps.upsert_lease(enriched)  # type: ignore[arg-type]
                _log.info(
                    "lease_enriched_from_tags",
                    lease_id=existing_lease.id,
                    tenant_id=tid,
                    fields=list(merged),
                )


async def _persist_delinquency_notes(
    row: dict[str, Any], ctx: IngestionCtx, tenant_id: str
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
        await _record_extracted(ctx, nid, "Note")


async def persist_lease(row: dict[str, Any], ctx: IngestionCtx) -> None:
    raw_mgr = str(
        row.get("_manager_tag") or row.get("site_manager_name") or row.get("manager_name") or ""
    ).strip()
    if raw_mgr:
        mgr_tag = _primary_manager_tag(raw_mgr)
        if is_manager_tag(mgr_tag):
            raw_addr = str(row.get("property_address", "")).strip()
            pid = _property_id(property_name(raw_addr) or raw_addr)
            ctx.prop_manager_tags[pid] = mgr_tag
            ctx.real_manager_tags.add(mgr_tag)

    prop_id = await _ensure_property(row, ctx)
    if prop_id is None:
        return  # lease expiration is authoritative; None only occurs on misconfigured rows
    unum = str(row.get("unit_number") or "main").strip()
    uid = _unit_id(prop_id, unum)
    tname = str(row.get("tenant_name") or row.get("name") or "").strip()
    if not tname:
        _log.debug("persist_lease_skipped_no_tenant", prop_id=prop_id, unum=unum)
        return
    tid = _tenant_id(tname, prop_id)
    lid = _lease_id(tname, prop_id, unum)
    rent = to_decimal(row.get("monthly_rent"))

    unit_proposed: dict[str, Any] = {"source_document_id": ctx.doc_id}
    sqft = to_int(row.get("sqft"))
    if sqft is not None:
        unit_proposed["sqft"] = sqft
    market = to_decimal_or_none(row.get("market_rent"))
    if market is not None:
        unit_proposed["market_rent"] = market
    beds = to_int(row.get("bedrooms"))
    if beds is not None:
        unit_proposed["bedrooms"] = beds
    baths_raw = row.get("bathrooms")
    if baths_raw is not None:
        with contextlib.suppress(ValueError, TypeError):
            unit_proposed["bathrooms"] = float(baths_raw)

    existing_unit = await ctx.ps.get_unit(uid)
    if existing_unit is not None:
        u_merged = _confidence_merge(existing_unit, unit_proposed, ctx.report_type, "Unit")
        u_merged["source_document_id"] = ctx.doc_id
        unit = existing_unit.model_copy(update=u_merged)
    else:
        unit = Unit(id=uid, property_id=prop_id, unit_number=unum, **unit_proposed)
    await ctx.ps.upsert_unit(_with_hash(unit))  # type: ignore[arg-type]
    await _record_extracted(ctx, uid, "Unit")

    tenant_proposed: dict[str, object] = {
        "name": tname,
        "phone": str(row.get("phone_numbers") or row.get("phone") or "").strip() or None,
        "source_document_id": ctx.doc_id,
    }
    existing_tenant = await ctx.ps.get_tenant(tid)
    if existing_tenant is not None:
        t_merged = _confidence_merge(existing_tenant, tenant_proposed, ctx.report_type, "Tenant")
        t_merged["source_document_id"] = ctx.doc_id
        tenant = existing_tenant.model_copy(update=t_merged)
    else:
        tenant = Tenant(id=tid, **tenant_proposed)  # type: ignore[arg-type]
    await ctx.ps.upsert_tenant(_with_hash(tenant))  # type: ignore[arg-type]
    await _record_extracted(ctx, tid, "Tenant")

    raw_tags = str(row.get("_manager_tag") or "").strip()
    tag_data: LeaseTagFields = parse_lease_tags(raw_tags)

    start = to_date(row.get("move_in_date") or row.get("start_date"))
    end = to_date(row.get("lease_expires") or row.get("end_date"))
    lease_kwargs: dict[str, Any] = {
        "id": lid,
        "unit_id": uid,
        "tenant_id": tid,
        "property_id": prop_id,
        "start_date": start or LEASE_START_FALLBACK,
        "end_date": end or LEASE_END_FALLBACK,
        "monthly_rent": rent,
        "status": LeaseStatus.ACTIVE,
        "source_document_id": ctx.doc_id,
    }
    market_lease = to_decimal_or_none(row.get("market_rent"))
    if market_lease is not None:
        lease_kwargs["market_rent"] = market_lease
    deposit = to_decimal_or_none(row.get("deposit"))
    if deposit is not None:
        lease_kwargs["deposit"] = deposit
    lease_kwargs.update(tag_data.lease_updates())
    if not lease_kwargs.get("is_month_to_month") and row.get("is_month_to_month"):
        lease_kwargs["is_month_to_month"] = True

    await _reconcile_lease(ctx, _with_hash(Lease(**lease_kwargs)))  # type: ignore[arg-type]
    await _record_extracted(ctx, lid, "Lease")


async def persist_property(row: dict[str, Any], ctx: IngestionCtx) -> None:
    await _ensure_property(row, ctx)


async def persist_maintenance(row: dict[str, Any], ctx: IngestionCtx) -> None:
    prop_id = await _ensure_property(row, ctx)
    if prop_id is None:
        raw_addr = str(row.get("property_address", "")).strip()
        _log.debug("persist_maintenance_skipped_no_property", raw_addr=raw_addr)
        return
    unum = str(row.get("unit_number") or row.get("unit_id") or "main").strip()
    uid = _unit_id(prop_id, unum)
    title = str(row.get("title") or "").strip()
    rid = _maintenance_id(prop_id, unum, title)
    cat = str(row.get("category") or "general").strip().lower()
    # Vocab maps "Status" → "tenant_status" generically; work-order reports
    # land here so check both keys.
    st = str(row.get("status") or row.get("tenant_status") or "open").strip().lower()
    pri = str(row.get("priority") or "medium").strip().lower()
    tname = str(row.get("tenant_name") or row.get("tenant_id") or "").strip()
    tid = _tenant_id(tname, prop_id) if tname else None
    vendor_name = str(row.get("vendor") or "").strip() or None
    vid = _vendor_id(vendor_name) if vendor_name else None
    scheduled = to_date(row.get("scheduled_date"))
    completed = to_date(row.get("completed_date") or row.get("completed_on"))
    resolved_at: datetime | None = None
    if (
        completed
        and MAINTENANCE_STATUS_MAP.get(st, MaintenanceStatus.OPEN) == MaintenanceStatus.COMPLETED
    ):
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
        id=oid,
        name=name,
        owner_type=otype,
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
        id=vid,
        name=name,
        category=TradeCategory(cat_raw)
        if cat_raw in {m.value for m in TradeCategory}
        else TradeCategory.GENERAL,
        phone=str(row.get("phone") or "").strip() or None,
        email=str(row.get("email") or "").strip() or None,
        is_internal=bool(row.get("is_internal", False)),
        source_document_id=ctx.doc_id,
    )
    await ctx.ps.upsert_vendor(_with_hash(vendor))  # type: ignore[arg-type]
    await _record_extracted(ctx, vid, "Vendor")


async def persist_manager(row: dict[str, Any], ctx: IngestionCtx) -> None:
    raw_name = str(
        row.get("site_manager_name") or row.get("name") or row.get("manager_name") or ""
    ).strip()

    mid: str | None = None
    if raw_name:
        mgr_name = manager_name_from_tag(raw_name)
        mid = _manager_id(mgr_name)
        tag = str(row.get("manager_tag") or raw_name).strip()
        existing = await ctx.ps.get_manager(mid)
        proposed: dict[str, str | int | None] = {
            "name": mgr_name,
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
                proposed[field] = raw
        raw_max = row.get("max_units")
        if raw_max is not None:
            with contextlib.suppress(TypeError, ValueError):
                proposed["max_units"] = int(raw_max)

        if existing is not None:
            merged = _confidence_merge(
                existing, proposed, ctx.report_type, "PropertyManager",  # type: ignore[arg-type]
            )
            merged["source_document_id"] = ctx.doc_id
            manager = existing.model_copy(update=merged)
        else:
            manager = PropertyManager(id=mid, **proposed)  # type: ignore[arg-type]
        await ctx.ps.upsert_manager(_with_hash(manager))  # type: ignore[arg-type]
        await _record_extracted(ctx, mid, "PropertyManager")

    if row.get("property_address"):
        prop_row = {**row, "type": "Property"}
        addr = str(row["property_address"])
        prop_id = _property_id(property_name(addr) or addr)
        if mid:
            ctx.property_manager[prop_id] = mid
        await _ensure_property(prop_row, ctx)

        unit_count = to_int(row.get("_unit_count"))
        if unit_count and unit_count == 1:
            uid = _unit_id(prop_id, "main")
            await ctx.ps.upsert_unit(
                _with_hash(
                    Unit(
                        id=uid,
                        property_id=prop_id,
                        unit_number="main",
                        source_document_id=ctx.doc_id,
                    )
                )
            )  # type: ignore[arg-type]
            await _record_extracted(ctx, uid, "Unit")


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
# Deterministic pipeline — called when a ReportProfile matches
# ---------------------------------------------------------------------------

_MANAGER_SCOPES = frozenset({"manager_portfolio", "single_property", "single_unit"})


async def run_deterministic_pipeline(
    *,
    ps: PropertyStore,
    doc_id: str,
    platform: str,
    result: IngestionResult,
    all_rows: list[dict[str, Any]],
    extract_data: dict[str, Any],
) -> None:
    """Execute the full ingestion pipeline without the workflow engine.

    *extract_data* is a dict with keys matching ``OrientResult`` —
    either from ``rules.build_orient_result`` (deterministic) or the
    ``orient`` LLM step (workflow fallback).
    """
    report_type = str(extract_data.get("report_type", "unknown"))
    scope = str(extract_data.get("scope", "unknown"))
    manager_name: str | None = extract_data.get("manager")
    column_map: dict[str, str] = extract_data.get("column_map", {})
    entity_type: str = extract_data.get("primary_entity_type", "")
    section_header: str | None = extract_data.get("section_header_column")
    as_of_date: date | None = extract_data.get("as_of_date")

    try:
        rt = ReportType(report_type)
    except ValueError:
        rt = ReportType.UNKNOWN

    ctx = IngestionCtx(
        platform=platform,
        report_type=rt,
        doc_id=doc_id,
        namespace="ingestion",
        ps=ps,
        manager_resolver=ManagerResolver(ps),
        result=result,
        as_of_date=as_of_date,
    )
    result.report_type = rt

    if manager_name and scope in _MANAGER_SCOPES:
        # Always query the store first.  ensure_manager does a three-tier
        # lookup (exact ID → normalized name → prefix) before creation.
        # is_manager_tag now only gates creation of *unknown* managers —
        # any manager already in the store is accepted regardless of whether
        # the raw tag would pass the heuristic.
        resolver = ManagerResolver(ps)
        resolution = await resolver.ensure_manager(manager_name)
        if resolution.manager_id:
            ctx.upload_manager_id = resolution.manager_id
            _log.info(
                "ingestion_manager_resolved",
                manager_id=resolution.manager_id,
                manager_name=resolution.manager_name,
                source="metadata",
                created_new=resolution.created_new,
                scope=scope,
                report_type=rt.value,
            )
        else:
            _log.info(
                "ingestion_manager_rejected",
                manager_name=manager_name,
                scope=scope,
                reason="not in store and failed is_manager_tag check",
            )

    mapped = apply_column_map(
        all_rows, column_map, entity_type, section_header_column=section_header,
    )
    _log.info(
        "deterministic_column_map",
        total_rows=len(all_rows),
        mapped_rows=len(mapped),
        entity_type=entity_type,
    )

    accepted = validate_rows(mapped, result)
    _log.info(
        "deterministic_validate",
        accepted=len(accepted),
        rejected=result.rows_rejected,
    )

    # Pre-pass: collect all manager tags across the entire document before
    # processing rows. Without this, a property encountered early (before its
    # manager tag row) is locked into seen_properties with no manager, and later
    # rows that do carry the tag can never update it.
    for row in mapped:
        raw_addr = str(row.get("property_address", "")).strip()
        if raw_addr:
            _pid = _property_id(property_name(raw_addr) or raw_addr)
            _pre_set_manager_tag(row, ctx, _pid)

    # Authority set for this report type — None means unknown/unconstrained.
    allowed_types = REPORT_CAN_CREATE.get(rt.value) if rt != ReportType.UNKNOWN else None

    for row in accepted:
        row_type = row.get("type", "")

        # Block rows whose entity type is not in this report's authority set.
        # This is the single guard against phantom entity creation (e.g. a
        # delinquency report spawning Unit records).
        if allowed_types is not None and row_type not in allowed_types:
            _log.info(
                "row_blocked_by_authority",
                report_type=rt.value,
                entity_type=row_type,
            )
            result.validation_warnings.append(
                RowWarning(
                    row_index=0,
                    row_type=row_type,
                    field="type",
                    issue=(
                        f"report type '{rt.value}' is not authorized to create"
                        f" '{row_type}' — row skipped"
                    ),
                    raw_value=row_type,
                )
            )
            result.rows_rejected += 1
            continue

        persister = ROW_PERSISTERS.get(row_type)
        if persister is None:
            result.observation_rows.append(row)
            result.rows_skipped += 1
            continue
        try:
            await persister(row, ctx)
        except Exception as exc:
            _log.warning(
                "row_persist_error", entity_type=row_type, error=str(exc), exc_info=True,
            )
            result.persist_errors.append(
                RowWarning(
                    row_index=0,
                    row_type=row_type,
                    field="",
                    issue="persistence failed",
                    raw_value=str(row)[:200],
                )
            )
            result.rows_rejected += 1
