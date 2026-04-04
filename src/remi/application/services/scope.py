"""Scope resolution — builds a typed ScopeContext for RE manager focus.

This module owns the RE-specific logic that converts a manager_id into
a domain-agnostic ScopeContext that the agent runtime consumes generically.
"""

from __future__ import annotations

import asyncio

import structlog

from remi.agent.runtime.deps import ScopeContext
from remi.application.core.protocols import PropertyStore

_log = structlog.get_logger(__name__)


async def resolve_manager_scope(
    property_store: PropertyStore,
    manager_id: str | None,
) -> ScopeContext:
    """Build a ScopeContext for the given manager, or empty if not scoped."""
    if not manager_id:
        return ScopeContext()
    try:
        mgr = await property_store.get_manager(manager_id)
        if mgr is None:
            return ScopeContext()

        portfolios = await property_store.list_portfolios(manager_id=manager_id)
        portfolio_props = await asyncio.gather(
            *[property_store.list_properties(portfolio_id=p.id) for p in portfolios]
        )
        all_props = [prop for props in portfolio_props for prop in props]
        unit_lists = await asyncio.gather(
            *[property_store.list_units(property_id=prop.id) for prop in all_props]
        )

        property_names = [prop.name for prop in all_props]
        total_units = sum(len(units) for units in unit_lists)
        prop_count = len(property_names)

        scope_parts = [
            f"## Manager Focus: {mgr.name}\n",
            f"The user has selected **{mgr.name}** (manager_id=`{manager_id}`).",
            f"This manager oversees {prop_count} properties "
            f"with {total_units} total units.",
        ]
        if property_names:
            scope_parts.append(
                "Properties: " + ", ".join(property_names[:20])
            )
        scope_parts.append(
            "\n**You MUST scope all tool calls to this manager.** "
            f'Always pass `manager_id="{manager_id}"` to onto_signals, '
            "onto_search, onto_aggregate, semantic_search, and any "
            "tool that accepts manager_id. "
            "Only discuss data relevant to this manager unless the user "
            "explicitly asks about the broader scope."
        )

        return ScopeContext(
            entity_id=manager_id,
            entity_name=mgr.name,
            entity_type="PropertyManager",
            scope_message="\n".join(scope_parts),
            tool_scope={"manager_id": manager_id},
        )
    except Exception:
        _log.warning(
            "manager_scope_resolve_failed",
            manager_id=manager_id,
            exc_info=True,
        )
        return ScopeContext(entity_id=manager_id)
