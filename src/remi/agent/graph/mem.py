"""In-memory implementations of MemoryStore and KnowledgeStore."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from remi.agent.graph.stores import KnowledgeStore, MemoryStore
from remi.agent.graph.types import Entity, MemoryEntry, Relationship


class InMemoryMemoryStore(MemoryStore):
    """Dict-backed key-value memory for development and testing."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, MemoryEntry]] = defaultdict(dict)

    async def store(self, namespace: str, key: str, value: str, *, ttl: int | None = None) -> None:
        self._data[namespace][key] = MemoryEntry(
            namespace=namespace,
            key=key,
            value=value,
            created_at=datetime.now(UTC),
        )

    async def recall(self, namespace: str, key: str) -> str | None:
        entry = self._data.get(namespace, {}).get(key)
        return entry.value if entry else None

    async def search(self, namespace: str, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        entries = list(self._data.get(namespace, {}).values())
        query_lower = query.lower()
        scored = []
        for entry in entries:
            val_str = entry.value.lower()
            key_str = entry.key.lower()
            if query_lower in val_str or query_lower in key_str:
                scored.append(entry)
        return scored[:limit]

    async def list_keys(self, namespace: str) -> list[str]:
        return list(self._data.get(namespace, {}).keys())


class InMemoryKnowledgeStore(KnowledgeStore):
    """Dict-backed entity/relationship graph for development and testing."""

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Entity]] = defaultdict(dict)
        self._relationships: dict[str, list[Relationship]] = defaultdict(list)

    async def put_entity(self, entity: Entity) -> None:
        now = datetime.now(UTC)
        if entity.created_at is None:
            entity.created_at = now
        entity.updated_at = now
        self._entities[entity.namespace][entity.entity_id] = entity

    async def get_entity(self, namespace: str, entity_id: str) -> Entity | None:
        return self._entities.get(namespace, {}).get(entity_id)

    async def find_entities(
        self,
        namespace: str,
        entity_type: str | None = None,
        query: str | None = None,
        *,
        limit: int = 20,
    ) -> list[Entity]:
        entities = list(self._entities.get(namespace, {}).values())

        if entity_type:
            entities = [e for e in entities if e.entity_type == entity_type]

        if query:
            q = query.lower()
            entities = [
                e
                for e in entities
                if q in e.entity_id.lower()
                or q in e.entity_type.lower()
                or q in str(e.properties).lower()
            ]

        return entities[:limit]

    async def put_relationship(self, rel: Relationship) -> None:
        self._relationships[rel.namespace].append(rel)

    async def get_relationships(
        self,
        namespace: str,
        entity_id: str,
        *,
        relation_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[Relationship]:
        rels = self._relationships.get(namespace, [])
        result = []
        for r in rels:
            matches_direction = (
                (direction == "outgoing" and r.source_id == entity_id)
                or (direction == "incoming" and r.target_id == entity_id)
                or (direction == "both" and (r.source_id == entity_id or r.target_id == entity_id))
            )
            if matches_direction and (relation_type is None or r.relation_type == relation_type):
                result.append(r)
        return result

    async def traverse(
        self,
        namespace: str,
        start_id: str,
        relation_types: list[str] | None = None,
        *,
        max_depth: int = 3,
    ) -> list[Entity]:
        visited: set[str] = set()
        result: list[Entity] = []
        queue: list[tuple[str, int]] = [(start_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            entity = await self.get_entity(namespace, current_id)
            if entity and current_id != start_id:
                result.append(entity)

            rels = await self.get_relationships(namespace, current_id, direction="outgoing")
            for rel in rels:
                if (
                    relation_types is None or rel.relation_type in relation_types
                ) and rel.target_id not in visited:
                    queue.append((rel.target_id, depth + 1))

        return result

    async def list_namespaces(self) -> list[str]:
        return list(self._entities.keys())

    async def delete_entity(self, namespace: str, entity_id: str) -> bool:
        if entity_id in self._entities.get(namespace, {}):
            del self._entities[namespace][entity_id]
            self._relationships[namespace] = [
                r
                for r in self._relationships.get(namespace, [])
                if r.source_id != entity_id and r.target_id != entity_id
            ]
            return True
        return False
