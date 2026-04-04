"""Source adapter protocol — normalises raw data from any source into
a common intermediate form before persistence.

Each adapter (AppFolio, Yardi, QuickBooks, …) implements this protocol.
The ingestion pipeline selects an adapter by source name and delegates
row normalisation and annotation extraction to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ReportTypeInfo:
    """Describes a report type an adapter can handle."""

    name: str
    description: str


@dataclass(frozen=True)
class ColumnMapping:
    """Maps raw source column names to canonical ontology field names."""

    entity_type: str
    raw_to_canonical: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedRow:
    """A single row normalised to the ontology's vocabulary."""

    entity_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnnotationData:
    """Semi-structured or unstructured text extracted alongside a row."""

    content: str
    annotation_type: str = "note"
    source_field: str = ""
    target_entity_type: str = ""
    target_entity_id: str = ""


@runtime_checkable
class SourceAdapter(Protocol):
    """Normalises raw source data into a common intermediate form."""

    @property
    def source_name(self) -> str: ...

    def supported_report_types(self) -> list[ReportTypeInfo]: ...

    def normalize_columns(
        self, raw_columns: list[str], report_type: str,
    ) -> list[ColumnMapping]: ...

    def normalize_row(
        self, row: dict[str, Any], report_type: str,
    ) -> NormalizedRow | None: ...

    def extract_annotations(
        self, row: dict[str, Any], report_type: str,
    ) -> list[AnnotationData]: ...


class AdapterRegistry:
    """Registry of source adapters, keyed by ``source_name``."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        self._adapters[adapter.source_name] = adapter

    def get(self, source_name: str) -> SourceAdapter | None:
        return self._adapters.get(source_name)

    def list_adapters(self) -> list[str]:
        return list(self._adapters.keys())
