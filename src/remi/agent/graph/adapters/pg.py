"""Postgres-backed KnowledgeStore — entities and relationships in SQL."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from remi.agent.db.tables import KGEntityRow, KGRelationshipRow
from remi.agent.graph.stores import KnowledgeStore
from remi.agent.graph.types import Entity, FactProvenance, Relationship

_log = structlog.get_logger(__name__)


def _entity_to_row(entity: Entity) -> KGEntityRow:
    return KGEntityRow(
        entity_id=entity.entity_id,
        namespace=entity.namespace,
        entity_type=entity.entity_type,
        properties=entity.properties,
        metadata_=entity.metadata,
        provenance=entity.provenance.model_dump(mode="json") if entity.provenance else None,
        created_at=entity.created_at or datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _row_to_entity(row: KGEntityRow) -> Entity:
    prov = FactProvenance.model_validate(row.provenance) if row.provenance else None
    return Entity(
        entity_id=row.entity_id,
        entity_type=row.entity_type,
        namespace=row.namespace,
        properties=row.properties or {},
        metadata=row.metadata_ or {},
        provenance=prov,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _rel_to_row(rel: Relationship) -> KGRelationshipRow:
    return KGRelationshipRow(
        source_id=rel.source_id,
        target_id=rel.target_id,
        relation_type=rel.relation_type,
        namespace=rel.namespace,
        properties=rel.properties,
        provenance=rel.provenance.model_dump(mode="json") if rel.provenance else None,
        weight=rel.weight,
        created_at=rel.created_at or datetime.now(UTC),
    )


def _row_to_rel(row: KGRelationshipRow) -> Relationship:
    prov = FactProvenance.model_validate(row.provenance) if row.provenance else None
    return Relationship(
        source_id=row.source_id,
        target_id=row.target_id,
        relation_type=row.relation_type,
        namespace=row.namespace,
        properties=row.properties or {},
        provenance=prov,
        weight=row.weight,
        created_at=row.created_at,
    )


class PostgresKnowledgeStore(KnowledgeStore):
    """Postgres-backed entity/relationship graph."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def put_entity(self, entity: Entity) -> None:
        now = datetime.now(UTC)
        if entity.created_at is None:
            entity.created_at = now
        entity.updated_at = now

        async with self._sf() as session:
            existing = await session.get(
                KGEntityRow, (entity.entity_id, entity.namespace),
            )
            if existing is not None:
                existing.entity_type = entity.entity_type
                existing.properties = entity.properties
                existing.metadata_ = entity.metadata
                existing.provenance = (
                    entity.provenance.model_dump(mode="json") if entity.provenance else None
                )
                existing.updated_at = now
                session.add(existing)
            else:
                session.add(_entity_to_row(entity))
            await session.commit()

    async def get_entity(self, namespace: str, entity_id: str) -> Entity | None:
        async with self._sf() as session:
            row = await session.get(KGEntityRow, (entity_id, namespace))
            return _row_to_entity(row) if row else None

    async def find_entities(
        self,
        namespace: str,
        entity_type: str | None = None,
        query: str | None = None,
        *,
        limit: int = 20,
    ) -> list[Entity]:
        async with self._sf() as session:
            stmt = select(KGEntityRow).where(
                col(KGEntityRow.namespace) == namespace,
            )
            if entity_type:
                stmt = stmt.where(col(KGEntityRow.entity_type) == entity_type)
            stmt = stmt.limit(limit)
            result = await session.exec(stmt)
            rows = result.all()

        entities = [_row_to_entity(r) for r in rows]
        if query:
            q = query.lower()
            entities = [
                e for e in entities
                if q in e.entity_id.lower()
                or q in e.entity_type.lower()
                or q in str(e.properties).lower()
            ]
        return entities

    async def put_relationship(self, rel: Relationship) -> None:
        async with self._sf() as session:
            stmt = select(KGRelationshipRow).where(
                col(KGRelationshipRow.source_id) == rel.source_id,
                col(KGRelationshipRow.target_id) == rel.target_id,
                col(KGRelationshipRow.relation_type) == rel.relation_type,
                col(KGRelationshipRow.namespace) == rel.namespace,
            )
            result = await session.exec(stmt)
            existing = result.first()
            if existing is not None:
                existing.properties = rel.properties
                existing.weight = rel.weight
                existing.provenance = (
                    rel.provenance.model_dump(mode="json") if rel.provenance else None
                )
                session.add(existing)
            else:
                session.add(_rel_to_row(rel))
            await session.commit()

    async def get_relationships(
        self,
        namespace: str,
        entity_id: str,
        *,
        relation_type: str | None = None,
        direction: str = "outgoing",
    ) -> list[Relationship]:
        async with self._sf() as session:
            stmt = select(KGRelationshipRow).where(
                col(KGRelationshipRow.namespace) == namespace,
            )
            if direction == "outgoing":
                stmt = stmt.where(col(KGRelationshipRow.source_id) == entity_id)
            elif direction == "incoming":
                stmt = stmt.where(col(KGRelationshipRow.target_id) == entity_id)
            else:
                from sqlalchemy import or_
                stmt = stmt.where(or_(
                    col(KGRelationshipRow.source_id) == entity_id,
                    col(KGRelationshipRow.target_id) == entity_id,
                ))
            if relation_type:
                stmt = stmt.where(col(KGRelationshipRow.relation_type) == relation_type)
            result = await session.exec(stmt)
            return [_row_to_rel(r) for r in result.all()]

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
        async with self._sf() as session:
            stmt = select(col(KGEntityRow.namespace)).distinct()
            result = await session.exec(stmt)
            return list(result.all())

    async def delete_entity(self, namespace: str, entity_id: str) -> bool:
        async with self._sf() as session:
            row = await session.get(KGEntityRow, (entity_id, namespace))
            if row is None:
                return False
            await session.delete(row)

            rel_stmt = select(KGRelationshipRow).where(
                col(KGRelationshipRow.namespace) == namespace,
            ).where(
                (col(KGRelationshipRow.source_id) == entity_id)
                | (col(KGRelationshipRow.target_id) == entity_id)
            )
            rel_result = await session.exec(rel_stmt)
            for rel_row in rel_result.all():
                await session.delete(rel_row)

            await session.commit()
            return True
