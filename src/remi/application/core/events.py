"""Domain change events — the vocabulary for how data changes flow through the system.

A ``ChangeSet`` is produced whenever new information enters REMI (file upload,
API mutation, AI correction, chat assertion).  Downstream consumers — the
PropertyStore, knowledge graph, and embedding pipeline — subscribe to
ChangeSets rather than being called directly by ingestion code.

``EventStore`` is the persistence protocol.  Implementations live in
``application/stores/``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from remi.application.core.models.enums import ReportType


class ChangeType(StrEnum):
    """What happened to the entity."""

    CREATED = "created"
    UPDATED = "updated"
    REMOVED = "removed"


class ChangeSource(StrEnum):
    """Where the change originated — determines conflict priority."""

    ADAPTER_IMPORT = "adapter_import"
    LLM_EXTRACTION = "llm_extraction"
    API_MUTATION = "api_mutation"
    AGENT_ASSERTION = "agent_assertion"
    MANAGER_CORRECTION = "manager_correction"


@dataclass(frozen=True, slots=True)
class FieldChange:
    """A single field-level delta."""

    field: str
    old_value: Any = None
    new_value: Any = None


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """A single entity-level change with field-level detail.

    Produced by the diff engine when comparing mapped records against
    the current PropertyStore state.
    """

    entity_type: str
    entity_id: str
    change_type: ChangeType
    fields: tuple[FieldChange, ...] = ()
    source: ChangeSource = ChangeSource.ADAPTER_IMPORT
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ChangeSet:
    """The complete result of diffing an upload against current state.

    One ChangeSet per upload / mutation batch.  This is the fundamental
    unit that downstream consumers react to.
    """

    id: str = field(default_factory=lambda: f"cs-{uuid4().hex[:12]}")
    source: ChangeSource = ChangeSource.ADAPTER_IMPORT
    source_detail: str = ""
    adapter_name: str = ""
    report_type: ReportType = ReportType.UNKNOWN
    document_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    created: list[ChangeEvent] = field(default_factory=list)
    updated: list[ChangeEvent] = field(default_factory=list)
    unchanged_ids: list[str] = field(default_factory=list)
    removed: list[ChangeEvent] = field(default_factory=list)

    @property
    def events(self) -> list[ChangeEvent]:
        return self.created + self.updated + self.removed

    @property
    def total_changes(self) -> int:
        return len(self.created) + len(self.updated) + len(self.removed)

    @property
    def is_empty(self) -> bool:
        return self.total_changes == 0

    def summary(self) -> dict[str, int]:
        return {
            "created": len(self.created),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged_ids),
            "removed": len(self.removed),
        }


class EventStore(abc.ABC):
    """Append-only store for ChangeSets — the system's audit trail."""

    @abc.abstractmethod
    async def append(self, changeset: ChangeSet) -> None: ...

    @abc.abstractmethod
    async def get(self, changeset_id: str) -> ChangeSet | None: ...

    @abc.abstractmethod
    async def list_by_entity(
        self,
        entity_id: str,
        *,
        limit: int = 50,
    ) -> list[ChangeSet]: ...

    @abc.abstractmethod
    async def list_recent(self, *, limit: int = 20) -> list[ChangeSet]: ...
