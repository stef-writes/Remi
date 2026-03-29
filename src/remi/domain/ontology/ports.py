"""OntologyStore port — the single interface agents use to query data,
traverse relationships, extend the schema, and codify operational knowledge.

Sits on top of PropertyStore + KnowledgeStore; implementations bridge
to those stores without replacing them.
"""

from __future__ import annotations

import abc
from typing import Any

from remi.domain.ontology.types import (
    KnowledgeProvenance,
    LinkTypeDef,
    ObjectTypeDef,
)


class OntologyStore(abc.ABC):
    """Unified ontology interface over structured and graph data."""

    # -- Schema ---------------------------------------------------------------

    @abc.abstractmethod
    async def list_object_types(self) -> list[ObjectTypeDef]:
        ...

    @abc.abstractmethod
    async def get_object_type(self, name: str) -> ObjectTypeDef | None:
        ...

    @abc.abstractmethod
    async def define_object_type(self, type_def: ObjectTypeDef) -> None:
        ...

    @abc.abstractmethod
    async def list_link_types(self) -> list[LinkTypeDef]:
        ...

    @abc.abstractmethod
    async def define_link_type(self, link_def: LinkTypeDef) -> None:
        ...

    # -- Objects --------------------------------------------------------------

    @abc.abstractmethod
    async def get_object(
        self, type_name: str, object_id: str
    ) -> dict[str, Any] | None:
        ...

    @abc.abstractmethod
    async def search_objects(
        self,
        type_name: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        ...

    @abc.abstractmethod
    async def put_object(
        self, type_name: str, object_id: str, properties: dict[str, Any]
    ) -> None:
        ...

    # -- Links ----------------------------------------------------------------

    @abc.abstractmethod
    async def get_links(
        self,
        object_id: str,
        *,
        link_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        ...

    @abc.abstractmethod
    async def put_link(
        self,
        source_id: str,
        link_type: str,
        target_id: str,
        *,
        properties: dict[str, Any] | None = None,
    ) -> None:
        ...

    @abc.abstractmethod
    async def traverse(
        self,
        start_id: str,
        link_types: list[str] | None = None,
        *,
        max_depth: int = 3,
    ) -> list[dict[str, Any]]:
        ...

    # -- Aggregation ----------------------------------------------------------

    @abc.abstractmethod
    async def aggregate(
        self,
        type_name: str,
        metric: str,
        field: str | None = None,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> Any:
        ...

    # -- Timeline -------------------------------------------------------------

    @abc.abstractmethod
    async def record_event(
        self,
        object_type: str,
        object_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        ...

    @abc.abstractmethod
    async def get_timeline(
        self,
        object_type: str,
        object_id: str,
        *,
        event_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        ...

    # -- Knowledge codification -----------------------------------------------

    @abc.abstractmethod
    async def codify(
        self,
        knowledge_type: str,
        data: dict[str, Any],
        *,
        provenance: KnowledgeProvenance = KnowledgeProvenance.INFERRED,
    ) -> str:
        """Store a piece of operational knowledge. Returns the entity ID."""
        ...
