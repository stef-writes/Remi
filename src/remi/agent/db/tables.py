"""SQLModel table definitions owned by the agent layer.

Agent-layer row classes live here — one table per agent subsystem that
needs Postgres persistence.  Application-domain tables belong in
``application.infra.stores.pg.tables``, not here.

Naming convention: ``<Entity>Row`` to distinguish from Pydantic DTOs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

_TZDateTime = sa.DateTime(timezone=True)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DocumentRow(SQLModel, table=True):
    __tablename__ = "documents"

    id: str = Field(primary_key=True)
    filename: str
    content_type: str = ""
    uploaded_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
    row_count: int = 0
    column_names: list[str] = Field(default_factory=list, sa_type=sa.JSON)
    rows: list[dict[str, Any]] = Field(default_factory=list, sa_type=sa.JSON)
    doc_metadata: dict[str, Any] = Field(default_factory=dict, sa_type=sa.JSON)


# ---------------------------------------------------------------------------
# Knowledge graph tables
# ---------------------------------------------------------------------------


class KGEntityRow(SQLModel, table=True):
    __tablename__ = "kg_entities"
    __table_args__ = (
        sa.Index("ix_kg_entities_ns_type", "namespace", "entity_type"),
    )

    entity_id: str = Field(primary_key=True)
    namespace: str = Field(primary_key=True)
    entity_type: str
    properties: dict[str, Any] = Field(default_factory=dict, sa_type=sa.JSON)
    metadata_: dict[str, Any] = Field(
        default_factory=dict, sa_type=sa.JSON, sa_column_kwargs={"key": "metadata"},
    )
    provenance: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class KGRelationshipRow(SQLModel, table=True):
    __tablename__ = "kg_relationships"
    __table_args__ = (
        sa.Index("ix_kg_rels_ns_source", "namespace", "source_id"),
        sa.Index("ix_kg_rels_ns_target", "namespace", "target_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source_id: str
    target_id: str
    relation_type: str
    namespace: str = "default"
    properties: dict[str, Any] = Field(default_factory=dict, sa_type=sa.JSON)
    provenance: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    weight: float = 1.0
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


# ---------------------------------------------------------------------------
# Signal and feedback tables
# ---------------------------------------------------------------------------


class SignalRow(SQLModel, table=True):
    __tablename__ = "signals"
    __table_args__ = (
        sa.Index("ix_signals_type", "signal_type"),
        sa.Index("ix_signals_entity", "entity_id"),
    )

    signal_id: str = Field(primary_key=True)
    signal_type: str
    severity: str
    entity_type: str
    entity_id: str
    entity_name: str = ""
    description: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict, sa_type=sa.JSON)
    detected_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
    provenance: str = "data_derived"


class SignalFeedbackRow(SQLModel, table=True):
    __tablename__ = "signal_feedback"
    __table_args__ = (
        sa.Index("ix_feedback_signal", "signal_id"),
        sa.Index("ix_feedback_type", "signal_type"),
    )

    feedback_id: str = Field(primary_key=True)
    signal_id: str
    signal_type: str
    outcome: str
    actor: str = ""
    notes: str = ""
    context: dict[str, Any] = Field(default_factory=dict, sa_type=sa.JSON)
    recorded_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


# ---------------------------------------------------------------------------
# Vector embeddings table (requires pgvector extension)
# ---------------------------------------------------------------------------


class MemoryEntryRow(SQLModel, table=True):
    __tablename__ = "memory_entries"
    __table_args__ = (
        sa.Index("ix_memory_ns_key", "namespace", "key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    namespace: str
    key: str
    value: str = ""
    ttl_seconds: int | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)


class VectorEmbeddingRow(SQLModel, table=True):
    __tablename__ = "vector_embeddings"
    __table_args__ = (
        sa.Index("ix_vec_source", "source_entity_id"),
        sa.Index("ix_vec_type", "source_entity_type"),
    )

    id: str = Field(primary_key=True)
    text: str = ""
    source_entity_id: str
    source_entity_type: str
    source_field: str = ""
    metadata_: dict[str, Any] = Field(
        default_factory=dict, sa_type=sa.JSON, sa_column_kwargs={"key": "metadata"},
    )
    created_at: datetime = Field(default_factory=_utcnow, sa_type=_TZDateTime)
    vector: list[float] = Field(default_factory=list, sa_type=sa.JSON)
