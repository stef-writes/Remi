"""AutoAssignService — KB-tag-based property-to-manager assignment."""

from __future__ import annotations

import structlog

from remi.agent.graph.stores import KnowledgeStore
from remi.application.core.protocols import PropertyStore
from remi.application.core.rules import manager_name_from_tag
from remi.application.services.monitoring.snapshots.service import SnapshotService
from remi.types.text import slugify

from ._models import AutoAssignResult

logger = structlog.get_logger(__name__)


class AutoAssignService:
    def __init__(
        self,
        property_store: PropertyStore,
        knowledge_store: KnowledgeStore,
        snapshot_service: SnapshotService,
    ) -> None:
        self._ps = property_store
        self._ks = knowledge_store
        self._snapshot = snapshot_service

    async def _collect_property_tags(self) -> dict[str, str]:
        prop_to_tag: dict[str, str] = {}
        namespaces = await self._ks.list_namespaces()
        for ns in namespaces:
            entities = await self._ks.find_entities(
                ns, entity_type="appfolio_property", limit=5000
            )
            for entity in entities:
                tag = entity.properties.get("manager_tag", "")
                if tag and tag.lower() != "month-to-month" and entity.entity_id not in prop_to_tag:
                    prop_to_tag[entity.entity_id] = tag
        return prop_to_tag

    async def _build_tag_to_portfolio(self) -> dict[str, str]:
        managers = await self._ps.list_managers()
        portfolios = await self._ps.list_portfolios()

        manager_id_to_portfolio: dict[str, str] = {}
        for p in portfolios:
            manager_id_to_portfolio.setdefault(p.manager_id, p.id)

        tag_to_portfolio: dict[str, str] = {}
        for m in managers:
            portfolio_id = manager_id_to_portfolio.get(m.id)
            if not portfolio_id:
                continue
            if m.manager_tag:
                tag_to_portfolio[m.manager_tag] = portfolio_id
            tag_to_portfolio[m.name] = portfolio_id
            mgr_name = manager_name_from_tag(m.manager_tag or m.name)
            tag_to_portfolio[mgr_name] = portfolio_id

        return tag_to_portfolio

    async def auto_assign(self) -> AutoAssignResult:
        all_props = await self._ps.list_properties()
        unassigned = [p for p in all_props if not p.portfolio_id]

        prop_to_tag = await self._collect_property_tags()

        if not unassigned:
            return AutoAssignResult(
                assigned=0,
                unresolved=0,
                tags_available=len(prop_to_tag),
                message="Nothing to assign",
            )

        tag_to_portfolio = await self._build_tag_to_portfolio()

        assigned = 0
        unresolved = 0

        for prop in unassigned:
            tag = prop_to_tag.get(prop.id, "")
            if not tag:
                unresolved += 1
                continue

            portfolio_id = tag_to_portfolio.get(tag)
            if not portfolio_id:
                mgr_name = manager_name_from_tag(tag)
                portfolio_id = tag_to_portfolio.get(mgr_name)

            if not portfolio_id:
                slug = slugify(f"portfolio:{manager_name_from_tag(tag)}")
                for key, pid in tag_to_portfolio.items():
                    if slugify(f"portfolio:{manager_name_from_tag(key)}") == slug:
                        portfolio_id = pid
                        break

            if not portfolio_id:
                unresolved += 1
                continue

            updated = prop.model_copy(update={"portfolio_id": portfolio_id})
            await self._ps.upsert_property(updated)
            assigned += 1

        try:
            await self._snapshot.capture()
        except Exception:
            logger.warning("snapshot_after_auto_assign_failed", exc_info=True)

        msg = (
            f"Assigned {assigned} properties to existing managers. "
            f"{unresolved} had no tag or no matching manager."
        )
        return AutoAssignResult(
            assigned=assigned,
            unresolved=unresolved,
            tags_available=len(prop_to_tag),
            message=msg,
        )
