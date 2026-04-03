"""Shared ingestion context and KB helpers used by persist + persisters."""

from __future__ import annotations

from typing import Any

import structlog

from remi.agent.graph.stores import KnowledgeStore
from remi.agent.graph.types import Entity, Relationship
from remi.domain.ingestion.base import IngestionResult
from remi.domain.ingestion.managers import ManagerResolver
from remi.domain.ingestion.resolver import parse_address, property_name
from remi.domain.portfolio.models import Property
from remi.domain.portfolio.protocols import PropertyStore
from remi.types.text import slugify

_log = structlog.get_logger(__name__)


class IngestionCtx:
    """Shared mutable state across rows in a single document."""

    __slots__ = (
        "platform", "report_type", "doc_id", "namespace",
        "kb", "ps", "manager_resolver", "result",
        "upload_portfolio_id", "seen_properties",
        "prop_manager_tags", "real_manager_tags", "property_portfolio",
    )

    def __init__(
        self, *, platform: str, report_type: str, doc_id: str,
        namespace: str, kb: KnowledgeStore, ps: PropertyStore,
        manager_resolver: ManagerResolver, result: IngestionResult,
        upload_portfolio_id: str | None,
    ) -> None:
        self.platform = platform
        self.report_type = report_type
        self.doc_id = doc_id
        self.namespace = namespace
        self.kb = kb
        self.ps = ps
        self.manager_resolver = manager_resolver
        self.result = result
        self.upload_portfolio_id = upload_portfolio_id
        self.seen_properties: set[str] = set()
        self.prop_manager_tags: dict[str, str] = {}
        self.real_manager_tags: set[str] = set()
        self.property_portfolio: dict[str, str] = {}


async def merge_kb(
    ctx: IngestionCtx, entity_id: str, entity_type: str,
    new_props: dict[str, str | int | float | bool | None],
) -> None:
    """Merge-upsert an entity into the knowledge graph."""
    existing = await ctx.kb.get_entity(ctx.namespace, entity_id)
    if existing:
        merged = {**existing.properties, **new_props}
        await ctx.kb.put_entity(Entity(
            entity_id=entity_id, entity_type=existing.entity_type,
            namespace=ctx.namespace, properties=merged,
        ))
    else:
        await ctx.kb.put_entity(Entity(
            entity_id=entity_id, entity_type=entity_type,
            namespace=ctx.namespace, properties=dict(new_props),
        ))


async def link(
    ctx: IngestionCtx, source: str, target: str, relation: str,
) -> None:
    """Create a relationship in the knowledge graph."""
    await ctx.kb.put_relationship(Relationship(
        source_id=source, target_id=target,
        relation_type=relation, namespace=ctx.namespace,
    ))


async def ensure_property(
    row: dict[str, Any], ctx: IngestionCtx, *,
    replace_units: bool = False, replace_leases: bool = False,
) -> str:
    """Ensure the property exists. Returns property_id."""
    raw_addr = str(row.get("property_address", "")).strip()
    name = property_name(raw_addr) or raw_addr
    prop_id = slugify(f"property:{name}")

    if prop_id in ctx.seen_properties:
        return prop_id
    ctx.seen_properties.add(prop_id)

    if replace_units:
        n = await ctx.ps.delete_units_by_property(prop_id)
        if n:
            _log.info("scoped_replace_units", property_id=prop_id, deleted=n)
    if replace_leases:
        n = await ctx.ps.delete_leases_by_property(prop_id)
        if n:
            _log.info("scoped_replace_leases", property_id=prop_id, deleted=n)

    if ctx.upload_portfolio_id is not None:
        pid = ctx.upload_portfolio_id
    elif prop_id in ctx.property_portfolio:
        pid = ctx.property_portfolio[prop_id]
    else:
        existing = await ctx.ps.get_property(prop_id)
        pid = (existing.portfolio_id if existing else None) or ""

    address = parse_address(raw_addr)
    await ctx.ps.upsert_property(Property(
        id=prop_id, portfolio_id=pid, name=name,
        address=address, source_document_id=ctx.doc_id,
    ))
    await merge_kb(ctx, prop_id, f"{ctx.platform}_property", {
        "name": name, "address": address.one_line(),
        "source_doc": ctx.doc_id,
    })
    ctx.result.entities_created += 1

    tag = ctx.prop_manager_tags.get(prop_id)
    if tag and tag in ctx.real_manager_tags:
        portfolio_id = await ctx.manager_resolver.ensure_manager(tag)
        ctx.property_portfolio[prop_id] = portfolio_id
    elif tag:
        ctx.result.manager_tags_skipped.append(tag)
    return prop_id
