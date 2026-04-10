"""REEntityViewEnricher — pre-fetches live operational data for resolved entities.

Implements the kernel's EntityViewEnricher protocol. When the GraphRetriever
resolves a PropertyManager or Property entity, this fetches the full operational
view (same data as manager_review / property detail) and renders it as a
condensed, token-budgeted context block.

The LLM receives this in its system context before the first token — common
questions about a named manager or property require zero tool calls.
"""

from __future__ import annotations

import asyncio

import structlog

from remi.agent.graph.retrieval.retriever import ResolvedEntity
from remi.application.portfolio.managers import ManagerResolver
from remi.application.portfolio.properties import PropertyResolver
from remi.application.portfolio.views import ManagerSummary, PropertyListItem

_log = structlog.get_logger(__name__)

_ENRICHABLE_TYPES = frozenset({"PropertyManager", "Property"})


class REEntityViewEnricher:
    """Fetches and renders operational views for RE entities.

    Enriches PropertyManager and Property entities. Other entity types
    (Tenant, Lease, Unit, etc.) are skipped — their data is available via
    tool calls when needed.
    """

    def __init__(
        self,
        manager_resolver: ManagerResolver,
        property_resolver: PropertyResolver,
    ) -> None:
        self._managers = manager_resolver
        self._properties = property_resolver

    async def enrich(
        self,
        entities: list[ResolvedEntity],
    ) -> dict[str, str]:
        targets = [e for e in entities if e.entity_type in _ENRICHABLE_TYPES]
        if not targets:
            return {}

        results = await asyncio.gather(
            *[self._enrich_one(e) for e in targets],
            return_exceptions=True,
        )
        out: dict[str, str] = {}
        for entity, result in zip(targets, results):
            if isinstance(result, Exception):
                _log.warning(
                    "entity_enrichment_failed",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    exc_info=result,
                )
            elif isinstance(result, str) and result:
                out[entity.entity_id] = result
        return out

    async def _enrich_one(self, entity: ResolvedEntity) -> str:
        if entity.entity_type == "PropertyManager":
            return await self._enrich_manager(entity.entity_id)
        if entity.entity_type == "Property":
            return await self._enrich_property(entity.entity_id)
        return ""

    async def _enrich_manager(self, manager_id: str) -> str:
        summary = await self._managers.aggregate_manager(manager_id)
        if summary is None:
            return ""
        return _render_manager(summary)

    async def _enrich_property(self, property_id: str) -> str:
        items = await self._properties.list_properties()
        prop = next((p for p in items if p.id == property_id), None)
        if prop is None:
            return ""
        return _render_property(prop)


# ---------------------------------------------------------------------------
# Renderers — condensed prose blocks, ~400-800 tokens per entity
# ---------------------------------------------------------------------------


def _render_manager(s: ManagerSummary) -> str:
    m = s.metrics
    cov = s.data_coverage

    lines: list[str] = [
        f"## Pre-fetched: Manager — {s.name} (id: {s.manager_id})",
        f"Company: {s.company or '—'} | Email: {s.email}",
        "",
        "### Portfolio Metrics",
        (
            f"- Properties: {s.property_count} | "
            f"Units: {m.total_units} (occupied: {m.occupied}, vacant: {m.vacant})"
        ),
        f"- Occupancy: {m.occupancy_rate:.1%}",
        (
            f"- Monthly revenue: ${m.total_actual_rent:,.0f} actual / "
            f"${m.total_market_rent:,.0f} market"
        ),
        f"- Loss to lease: ${m.loss_to_lease:,.0f}/mo | Vacancy loss: ${m.vacancy_loss:,.0f}/mo",
        (
            f"- Open maintenance: {m.open_maintenance}"
            + (f" (emergency: {s.emergency_maintenance})" if s.emergency_maintenance else "")
        ),
        f"- Expiring leases (90d): {m.expiring_leases_90d} | Expired: {s.expired_leases}",
        (
            f"- Delinquency: {s.delinquent_count} tenants, "
            f"${s.total_delinquent_balance:,.0f} balance"
        ),
        f"- Below-market units: {s.below_market_units}",
        f"- Data confidence: {cov.confidence}",
    ]

    if cov.caveat:
        lines.append(f"- Caveat: {cov.caveat}")

    if s.properties:
        lines.append("\n### Properties")
        for p in s.properties:
            prop_line = (
                f"- **{p.property_name}**: {p.total_units} units, "
                f"{p.occupied} occupied ({p.occupancy_rate:.1%}), "
                f"${p.monthly_actual:,.0f}/mo actual"
            )
            flags: list[str] = []
            if p.emergency_maintenance:
                flags.append(f"emergency maintenance: {p.emergency_maintenance}")
            if p.expired_leases:
                flags.append(f"expired leases: {p.expired_leases}")
            if p.below_market_units:
                flags.append(f"below-market units: {p.below_market_units}")
            if flags:
                prop_line += f" | {', '.join(flags)}"
            lines.append(prop_line)

    if s.top_issues:
        lines.append("\n### Top Issues")
        for issue in s.top_issues[:5]:
            lines.append(
                f"- {issue.property_name}, Unit {issue.unit_number}: "
                f"{', '.join(issue.issues)}"
                + (f" (${issue.monthly_impact:,.0f}/mo impact)" if issue.monthly_impact else "")
            )

    lines.append(
        "\nThis data was pre-fetched. Use it to answer questions about this manager "
        "without calling manager_review. Call tools only for deeper drill-down "
        "(e.g., individual tenant names, rent roll details)."
    )
    return "\n".join(lines)


def _render_property(p: PropertyListItem) -> str:
    occ_rate = p.occupied / p.total_units if p.total_units else 0.0
    lines: list[str] = [
        f"## Pre-fetched: Property — {p.name} (id: {p.id})",
        f"Address: {p.address} | Type: {p.type}",
        f"Manager: {p.manager_id or '—'} | Owner: {p.owner_name or '—'}",
        "",
        "### Metrics",
        f"- Units: {p.total_units} | Occupied: {p.occupied} | Vacant: {p.total_units - p.occupied}",
        f"- Occupancy: {occ_rate:.1%}",
        "\nThis data was pre-fetched. Call tools for rent roll or maintenance detail.",
    ]
    return "\n".join(lines)
