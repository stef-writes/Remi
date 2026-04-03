"""Row-level validation between LLM extraction and persistence.

Validates extracted rows before they reach the resolver.  Rows that fail
critical checks (no address, unrecognised type) are quarantined into
``IngestionResult.ambiguous_rows``.  Rows that pass critical checks but
have field-level issues (out-of-range rent, unparseable date) get warnings
appended to ``IngestionResult.validation_warnings`` and are still forwarded.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from remi.domain.ingestion.base import IngestionResult, RowWarning
from remi.domain.ingestion.resolver import PERSISTABLE_TYPES, resolve_row_type

_log = structlog.get_logger(__name__)

_MAX_MONTHLY_RENT = Decimal("100_000")
_MAX_BALANCE = Decimal("1_000_000")
_MAX_SQFT = 50_000
_MAX_COST = Decimal("10_000_000")


def validate_rows(
    rows: list[dict[str, Any]],
    result: IngestionResult,
) -> list[dict[str, Any]]:
    """Validate extracted rows.  Returns accepted rows only.

    Populates ``result.validation_warnings``, ``result.ambiguous_rows``,
    ``result.rows_accepted``, and ``result.rows_rejected``.
    """
    accepted: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        warnings: list[RowWarning] = []
        reject = False

        raw_type = str(row.get("type", "raw_row"))
        resolved_type = resolve_row_type(raw_type)

        if resolved_type not in PERSISTABLE_TYPES:
            result.ambiguous_rows.append(row)
            result.rows_rejected += 1
            _log.info("row_rejected_unknown_type", row_index=idx, raw_type=raw_type)
            continue

        address = str(row.get("property_address", "")).strip()
        if not address:
            warnings.append(RowWarning(
                row_index=idx, row_type=resolved_type,
                field="property_address", issue="missing_required",
                raw_value="",
            ))
            reject = True

        type_validator = _TYPE_VALIDATORS.get(resolved_type)
        if type_validator is not None:
            type_warnings, type_reject = type_validator(idx, resolved_type, row)
            warnings.extend(type_warnings)
            reject = reject or type_reject

        if reject:
            result.ambiguous_rows.append(row)
            result.rows_rejected += 1
            result.validation_warnings.extend(warnings)
            _log.info(
                "row_rejected",
                row_index=idx,
                row_type=resolved_type,
                issues=[w.issue for w in warnings],
            )
        else:
            if warnings:
                result.validation_warnings.extend(warnings)
            result.rows_accepted += 1
            accepted.append(row)

    if result.rows_rejected:
        _log.warning(
            "validation_summary",
            accepted=result.rows_accepted,
            rejected=result.rows_rejected,
            warning_count=len(result.validation_warnings),
        )

    return accepted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ValidatorResult = tuple[list[RowWarning], bool]


def _try_decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _try_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _check_non_negative(
    idx: int,
    row_type: str,
    row: dict[str, Any],
    field_name: str,
    *,
    ceiling: Decimal | None = None,
) -> RowWarning | None:
    raw = row.get(field_name)
    if raw is None:
        return None
    d = _try_decimal(raw)
    if d is None:
        return RowWarning(
            row_index=idx, row_type=row_type, field=field_name,
            issue="parse_failed", raw_value=str(raw)[:80],
        )
    if d < 0:
        return RowWarning(
            row_index=idx, row_type=row_type, field=field_name,
            issue="negative_value", raw_value=str(raw)[:80],
        )
    if ceiling is not None and d > ceiling:
        return RowWarning(
            row_index=idx, row_type=row_type, field=field_name,
            issue="out_of_range", raw_value=str(raw)[:80],
        )
    return None


def _check_positive_int(
    idx: int,
    row_type: str,
    row: dict[str, Any],
    field_name: str,
    *,
    ceiling: int | None = None,
) -> RowWarning | None:
    raw = row.get(field_name)
    if raw is None:
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return RowWarning(
            row_index=idx, row_type=row_type, field=field_name,
            issue="parse_failed", raw_value=str(raw)[:80],
        )
    if v < 0:
        return RowWarning(
            row_index=idx, row_type=row_type, field=field_name,
            issue="negative_value", raw_value=str(raw)[:80],
        )
    if ceiling is not None and v > ceiling:
        return RowWarning(
            row_index=idx, row_type=row_type, field=field_name,
            issue="out_of_range", raw_value=str(raw)[:80],
        )
    return None


# ---------------------------------------------------------------------------
# Per-type validators
# ---------------------------------------------------------------------------


def _validate_unit(idx: int, row_type: str, row: dict[str, Any]) -> _ValidatorResult:
    warnings: list[RowWarning] = []

    for field_name in ("market_rent", "monthly_rent", "current_rent"):
        w = _check_non_negative(idx, row_type, row, field_name, ceiling=_MAX_MONTHLY_RENT)
        if w:
            warnings.append(w)

    w = _check_positive_int(idx, row_type, row, "sqft", ceiling=_MAX_SQFT)
    if w:
        warnings.append(w)

    w = _check_positive_int(idx, row_type, row, "days_vacant")
    if w:
        warnings.append(w)

    return warnings, False


def _validate_tenant(idx: int, row_type: str, row: dict[str, Any]) -> _ValidatorResult:
    warnings: list[RowWarning] = []
    reject = False

    tenant_name = str(row.get("tenant_name") or row.get("name") or "").strip()
    if not tenant_name:
        warnings.append(RowWarning(
            row_index=idx, row_type=row_type,
            field="tenant_name", issue="missing_required",
            raw_value="",
        ))
        reject = True

    for field_name in ("balance_owed", "amount_owed", "balance_0_30", "balance_30_plus"):
        ceiling = _MAX_BALANCE if field_name in ("amount_owed", "balance_owed") else None
        w = _check_non_negative(idx, row_type, row, field_name, ceiling=ceiling)
        if w:
            warnings.append(w)

    return warnings, reject


def _validate_lease(idx: int, row_type: str, row: dict[str, Any]) -> _ValidatorResult:
    warnings: list[RowWarning] = []

    tenant_name = str(row.get("tenant_name") or row.get("name") or "").strip()
    if not tenant_name:
        warnings.append(RowWarning(
            row_index=idx, row_type=row_type,
            field="tenant_name", issue="missing_required",
            raw_value="",
        ))

    w = _check_non_negative(idx, row_type, row, "monthly_rent", ceiling=_MAX_MONTHLY_RENT)
    if w:
        warnings.append(w)

    start_raw = row.get("move_in_date") or row.get("start_date")
    end_raw = row.get("lease_expires") or row.get("end_date")
    start = _try_date(start_raw)
    end = _try_date(end_raw)

    if start_raw is not None and start is None:
        warnings.append(RowWarning(
            row_index=idx, row_type=row_type,
            field="start_date", issue="parse_failed",
            raw_value=str(start_raw)[:80],
        ))
    if end_raw is not None and end is None:
        warnings.append(RowWarning(
            row_index=idx, row_type=row_type,
            field="end_date", issue="parse_failed",
            raw_value=str(end_raw)[:80],
        ))
    if start and end and start > end:
        warnings.append(RowWarning(
            row_index=idx, row_type=row_type,
            field="start_date/end_date", issue="inverted_range",
            raw_value=f"{start.isoformat()} > {end.isoformat()}",
        ))

    return warnings, False


def _validate_maintenance(idx: int, row_type: str, row: dict[str, Any]) -> _ValidatorResult:
    warnings: list[RowWarning] = []

    title = str(row.get("title") or "").strip()
    if not title:
        warnings.append(RowWarning(
            row_index=idx, row_type=row_type,
            field="title", issue="missing_required",
            raw_value="",
        ))

    w = _check_non_negative(idx, row_type, row, "cost", ceiling=_MAX_COST)
    if w:
        warnings.append(w)

    return warnings, False


_TYPE_VALIDATORS: dict[
    str,
    Callable[[int, str, dict[str, Any]], _ValidatorResult],
] = {
    "Unit": _validate_unit,
    "Tenant": _validate_tenant,
    "Lease": _validate_lease,
    "MaintenanceRequest": _validate_maintenance,
}
