"""BridgedKnowledgeGraph — routes knowledge graph calls to a domain store
and KnowledgeStore without replacing them.

Part of the **Incline** framework. Domain-agnostic: the caller provides
``core_types`` — a mapping of type names to (get_one, list_all) callables
on whatever domain store the product uses. REMI passes PropertyStore
methods; a health product would pass PatientStore methods.

Non-core / dynamically discovered types go through KnowledgeStore.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from remi.models.memory import Entity, KnowledgeStore, Relationship
from remi.models.ontology import (
    KnowledgeGraph,
    KnowledgeProvenance,
    LinkTypeDef,
    ObjectTypeDef,
)

_NS = "ontology"

CoreTypeBindings = dict[str, tuple[Any, Any]]


def _model_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return dict(obj) if hasattr(obj, "__iter__") else {"value": str(obj)}


def _match_filters(obj: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        obj_val = obj.get(key)
        if isinstance(obj_val, str) and isinstance(value, str):
            if obj_val.lower() != value.lower():
                return False
        elif obj_val != value:
            return False
    return True


class BridgedKnowledgeGraph(KnowledgeGraph):
    """Routes knowledge graph calls to domain-specific stores + KnowledgeStore.

    ``core_types`` maps entity type names to ``(get_one, list_all)``
    callables on the domain store. Everything else falls through to
    ``KnowledgeStore``.
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        *,
        core_types: CoreTypeBindings | None = None,
    ) -> None:
        self._ks = knowledge_store
        self._core_types: CoreTypeBindings = core_types or {}

        self._type_registry: dict[str, ObjectTypeDef] = {}
        self._link_registry: dict[str, LinkTypeDef] = {}

    def _is_core(self, type_name: str) -> bool:
        return type_name in self._core_types

    # -- Schema ---------------------------------------------------------------

    async def list_object_types(self) -> list[ObjectTypeDef]:
        return list(self._type_registry.values())

    async def get_object_type(self, name: str) -> ObjectTypeDef | None:
        return self._type_registry.get(name)

    async def define_object_type(self, type_def: ObjectTypeDef) -> None:
        self._type_registry[type_def.name] = type_def

    async def list_link_types(self) -> list[LinkTypeDef]:
        return list(self._link_registry.values())

    async def define_link_type(self, link_def: LinkTypeDef) -> None:
        self._link_registry[link_def.name] = link_def

    # -- Objects --------------------------------------------------------------

    async def get_object(self, type_name: str, object_id: str) -> dict[str, Any] | None:
        if self._is_core(type_name):
            get_fn, _ = self._core_types[type_name]
            obj = await get_fn(object_id)
            return _model_to_dict(obj) if obj else None

        entity = await self._ks.get_entity(_NS, object_id)
        if entity and entity.entity_type == type_name:
            return {"id": entity.entity_id, **entity.properties}
        return None

    async def search_objects(
        self,
        type_name: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._is_core(type_name):
            _, list_fn = self._core_types[type_name]
            raw = await list_fn()
            items = [_model_to_dict(obj) for obj in raw]
        else:
            entities = await self._ks.find_entities(_NS, entity_type=type_name, limit=limit * 2)
            items = [{"id": e.entity_id, **e.properties} for e in entities]

        if filters:
            items = [i for i in items if _match_filters(i, filters)]

        if order_by:
            desc = order_by.startswith("-")
            field = order_by.lstrip("-")
            items.sort(key=lambda x: x.get(field, ""), reverse=desc)

        return items[:limit]

    async def put_object(self, type_name: str, object_id: str, properties: dict[str, Any]) -> None:
        entity = Entity(
            entity_id=object_id,
            entity_type=type_name,
            namespace=_NS,
            properties=properties,
        )
        await self._ks.put_entity(entity)

    # -- Links ----------------------------------------------------------------

    async def get_links(
        self,
        object_id: str,
        *,
        link_type: str | None = None,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        rels = await self._ks.get_relationships(
            _NS, object_id, relation_type=link_type, direction=direction
        )
        return [
            {
                "source_id": r.source_id,
                "target_id": r.target_id,
                "link_type": r.relation_type,
                **r.properties,
            }
            for r in rels
        ]

    async def put_link(
        self,
        source_id: str,
        link_type: str,
        target_id: str,
        *,
        properties: dict[str, Any] | None = None,
    ) -> None:
        rel = Relationship(
            source_id=source_id,
            target_id=target_id,
            relation_type=link_type,
            namespace=_NS,
            properties=properties or {},
            created_at=datetime.now(UTC),
        )
        await self._ks.put_relationship(rel)

    async def traverse(
        self,
        start_id: str,
        link_types: list[str] | None = None,
        *,
        max_depth: int = 3,
    ) -> list[dict[str, Any]]:
        entities = await self._ks.traverse(
            _NS, start_id, relation_types=link_types, max_depth=max_depth
        )
        return [{"id": e.entity_id, "type": e.entity_type, **e.properties} for e in entities]

    # -- Aggregation ----------------------------------------------------------

    async def aggregate(
        self,
        type_name: str,
        metric: str,
        field: str | None = None,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> Any:
        items = await self.search_objects(type_name, filters=filters, limit=10_000)

        if group_by:
            groups: dict[str, list[dict[str, Any]]] = {}
            for item in items:
                key = str(item.get(group_by, "unknown"))
                groups.setdefault(key, []).append(item)
            return {k: self._compute(metric, v, field) for k, v in groups.items()}

        return self._compute(metric, items, field)

    @staticmethod
    def _compute(metric: str, items: list[dict[str, Any]], field: str | None) -> Any:
        if metric == "count":
            return len(items)
        if not field:
            return None

        values = []
        for item in items:
            val = item.get(field)
            if val is not None:
                try:
                    values.append(Decimal(str(val)))
                except Exception:
                    continue

        if not values:
            return None

        if metric == "sum":
            return float(sum(values))
        if metric == "avg":
            return float(sum(values) / len(values))
        if metric == "min":
            return float(min(values))
        if metric == "max":
            return float(max(values))
        return None

    # -- Timeline -------------------------------------------------------------

    async def record_event(
        self,
        object_type: str,
        object_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        event_id = f"event:{uuid.uuid4().hex[:12]}"
        entity = Entity(
            entity_id=event_id,
            entity_type="event",
            namespace=_NS,
            properties={
                "object_type": object_type,
                "object_id": object_id,
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        await self._ks.put_entity(entity)

    async def get_timeline(
        self,
        object_type: str,
        object_id: str,
        *,
        event_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        all_events = await self._ks.find_entities(_NS, entity_type="event", limit=limit * 5)
        results = []
        for e in all_events:
            if (
                e.properties.get("object_type") == object_type
                and e.properties.get("object_id") == object_id
            ):
                if event_types and e.properties.get("event_type") not in event_types:
                    continue
                results.append({"id": e.entity_id, **e.properties})

        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return results[:limit]

    # -- Knowledge codification -----------------------------------------------

    async def codify(
        self,
        knowledge_type: str,
        data: dict[str, Any],
        *,
        provenance: KnowledgeProvenance = KnowledgeProvenance.INFERRED,
    ) -> str:
        entity_id = f"{knowledge_type}:{uuid.uuid4().hex[:12]}"
        entity = Entity(
            entity_id=entity_id,
            entity_type=knowledge_type,
            namespace=_NS,
            properties={**data, "provenance": provenance.value},
        )
        await self._ks.put_entity(entity)
        return entity_id


# Backward compatibility
BridgedOntologyStore = BridgedKnowledgeGraph
