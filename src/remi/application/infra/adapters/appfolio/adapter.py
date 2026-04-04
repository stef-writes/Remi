"""AppFolio source adapter — normalises AppFolio report data.

Implements ``SourceAdapter`` for AppFolio property management reports
(rent roll, delinquency, lease expiration, property directory).  Column
mappings and enum normalisations that were previously scattered across
``resolver.py`` and ``persisters.py`` are consolidated here.
"""

from __future__ import annotations

from typing import Any

from remi.application.infra.adapters.appfolio.schema import (
    REPORT_TYPE_DESCRIPTIONS,
)
from remi.application.infra.adapters.protocol import (
    AnnotationData,
    ColumnMapping,
    NormalizedRow,
    ReportTypeInfo,
)

_COLUMN_MAPS: dict[str, dict[str, dict[str, str]]] = {
    "rent_roll": {
        "Unit": {
            "Unit": "unit_number",
            "Beds": "bedrooms",
            "Baths": "bathrooms",
            "Sq Ft": "sqft",
            "Status": "occupancy_status",
            "Market Rent": "market_rent",
            "Rent": "monthly_rent",
            "Days Vacant": "days_vacant",
        },
    },
    "delinquency": {
        "Tenant": {
            "Tenant": "tenant_name",
            "Unit": "unit_number",
            "Status": "tenant_status",
            "Amount Owed": "amount_owed",
            "Balance": "balance_owed",
            "0-30": "balance_0_30",
            "30+": "balance_30_plus",
            "Last Payment": "last_payment_date",
            "Notes": "notes",
        },
    },
    "lease_expiration": {
        "Lease": {
            "Tenant": "tenant_name",
            "Unit": "unit_number",
            "Move In": "move_in_date",
            "Lease Expires": "lease_expires",
            "Rent": "monthly_rent",
            "Market Rent": "market_rent",
            "Sq Ft": "sqft",
            "Tags": "tags",
        },
    },
    "property_directory": {
        "Property": {
            "Property": "property_address",
            "Manager": "manager_name",
            "Address": "property_address",
        },
    },
}

_NOTE_FIELDS = ("notes", "delinquency_notes", "delinquent_notes", "description", "comments")

_TYPE_RESOLVE: dict[str, str] = {
    "rent_roll": "Unit",
    "delinquency": "Tenant",
    "lease_expiration": "Lease",
    "property_directory": "Property",
}


class AppFolioAdapter:
    """Normalises AppFolio property management report data."""

    @property
    def source_name(self) -> str:
        return "appfolio"

    def supported_report_types(self) -> list[ReportTypeInfo]:
        return [
            ReportTypeInfo(name=rt.value, description=desc)
            for rt, desc in REPORT_TYPE_DESCRIPTIONS.items()
        ]

    def normalize_columns(
        self, raw_columns: list[str], report_type: str,
    ) -> list[ColumnMapping]:
        maps = _COLUMN_MAPS.get(report_type, {})
        return [
            ColumnMapping(entity_type=etype, raw_to_canonical=col_map)
            for etype, col_map in maps.items()
        ]

    def normalize_row(
        self, row: dict[str, Any], report_type: str,
    ) -> NormalizedRow | None:
        entity_type = row.get("type") or _TYPE_RESOLVE.get(report_type)
        if not entity_type:
            return None

        maps = _COLUMN_MAPS.get(report_type, {})
        type_map = maps.get(entity_type, {})

        fields: dict[str, Any] = {}
        for raw_key, value in row.items():
            canonical = type_map.get(raw_key, raw_key)
            fields[canonical] = value

        return NormalizedRow(
            entity_type=entity_type,
            fields=fields,
            confidence=0.85,
            raw=dict(row),
        )

    def extract_annotations(
        self, row: dict[str, Any], report_type: str,
    ) -> list[AnnotationData]:
        annotations: list[AnnotationData] = []
        for field_name in _NOTE_FIELDS:
            raw = str(row.get(field_name) or "").strip()
            if not raw:
                continue
            for line in raw.splitlines():
                line = line.strip()
                if line:
                    annotations.append(AnnotationData(
                        content=line,
                        annotation_type="note",
                        source_field=field_name,
                    ))
        return annotations
