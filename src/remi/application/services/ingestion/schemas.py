"""Pydantic output schemas for ingestion workflow LLM steps.

These models validate the structured JSON output from LLM nodes in the
document_ingestion and graph_ingest workflow YAMLs. They're registered
as ``output_schema`` references in the YAML and resolved by the engine
at runtime.

The schemas enforce that the LLM produced usable data before the
pipeline proceeds to mapping and persistence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# document_ingestion: extract step output
# ---------------------------------------------------------------------------


class ExtractResult(BaseModel):
    """Validated output from the document_ingestion ``extract`` step."""

    report_type: str = "unknown"
    platform: str = "appfolio"
    manager: str | None = None
    scope: str = "unknown"
    effective_date: str | None = None
    date_range_start: str | None = None
    date_range_end: str | None = None
    primary_entity_type: str = ""
    column_map: dict[str, str] = Field(default_factory=dict)
    section_header_column: str | None = None
    observations_likely: bool = False
    unknown_columns: list[str] = Field(default_factory=list)
    needs_inspection: bool = False


# ---------------------------------------------------------------------------
# document_ingestion: inspect step output
# ---------------------------------------------------------------------------


class AmbiguousColumn(BaseModel):
    """A column whose mapping was uncertain and how it was resolved."""

    column: str
    original_mapping: str
    corrected_mapping: str
    reason: str


class InspectResult(BaseModel):
    """Validated output from the document_ingestion ``inspect`` step.

    The inspect step sees real row values and corrects any ambiguous column
    mappings that the extract step got wrong from headers alone.
    """

    column_map: dict[str, str] = Field(default_factory=dict)
    ambiguous_columns: list[AmbiguousColumn] = Field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# document_ingestion: capture step output
# ---------------------------------------------------------------------------


class CapturedEntity(BaseModel):
    entity_type: str
    entity_id: str
    properties: dict[str, object] = Field(default_factory=dict)
    relationships: list[dict[str, str]] = Field(default_factory=list)


class CaptureResult(BaseModel):
    """Validated output from the document_ingestion ``capture`` step."""

    captured: list[CapturedEntity] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# graph_ingest: reason step output
# ---------------------------------------------------------------------------


class GraphOperation(BaseModel):
    """A single graph operation produced by the reasoning step."""

    op: str
    type: str = ""
    id: str = ""
    properties: dict[str, object] = Field(default_factory=dict)
    identity_note: str | None = None
    source_id: str = ""
    target_id: str = ""
    relation: str = ""
    proposed_type: str = ""
    description: str = ""
    fields: list[str] = Field(default_factory=list)
    sample: dict[str, object] = Field(default_factory=dict)
    reason: str = ""
    input_value: str = ""
    candidate_id: str = ""
    confidence: float = 0.0


class GraphReasonResult(BaseModel):
    """Validated output from the graph_ingest ``reason`` step."""

    report_type: str = "unknown"
    platform: str = "appfolio"
    manager: str | None = None
    total_entities: int = 0
    operations: list[GraphOperation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# graph_ingest: extend step output
# ---------------------------------------------------------------------------


class ProposedField(BaseModel):
    name: str
    type: str = "str"
    required: bool = False
    description: str = ""


class ProposedRelationship(BaseModel):
    relation: str
    target_type: str
    direction: str = "outbound"
    description: str = ""


class ProposedType(BaseModel):
    type_name: str
    description: str = ""
    fields: list[ProposedField] = Field(default_factory=list)
    relationships: list[ProposedRelationship] = Field(default_factory=list)
    reasoning: str = ""


class GraphExtendResult(BaseModel):
    """Validated output from the graph_ingest ``extend`` step."""

    proposed_types: list[ProposedType] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema registry — maps YAML output_schema names to Pydantic models
# ---------------------------------------------------------------------------

INGESTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "ExtractResult": ExtractResult,
    "InspectResult": InspectResult,
    "CaptureResult": CaptureResult,
    "GraphReasonResult": GraphReasonResult,
    "GraphExtendResult": GraphExtendResult,
}
