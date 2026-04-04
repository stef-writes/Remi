"""Entity text extraction for the embedding pipeline — PropertyStore entities.

Each function takes a PropertyStore and returns a list of EmbeddingRequest
objects. The EmbeddingPipeline calls these to gather text that needs
vectorising, then handles batching and storage.

Multi-source extractors (managers, document rows) live in
``extraction_sources.py``.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from remi.agent.vectors.types import EmbeddingRequest
from remi.application.core.protocols import PropertyStore

_log = structlog.get_logger(__name__)


def _decimal_str(d: Decimal) -> str:
    return f"${d:,.2f}" if d else ""


async def extract_tenants(ps: PropertyStore) -> list[EmbeddingRequest]:
    tenants = await ps.list_tenants()
    requests: list[EmbeddingRequest] = []

    for t in tenants:
        parts = [f"Tenant: {t.name}"]
        if t.status:
            parts.append(f"Status: {t.status.value}")
        if t.balance_owed > 0:
            parts.append(f"Balance owed: {_decimal_str(t.balance_owed)}")
        if t.balance_30_plus > 0:
            parts.append(f"Balance 30+ days: {_decimal_str(t.balance_30_plus)}")
        if t.tags:
            parts.append(f"Tags: {', '.join(t.tags)}")
        if t.last_payment_date:
            parts.append(f"Last payment: {t.last_payment_date.isoformat()}")

        text = ". ".join(parts)
        if len(text.strip()) < 10:
            continue

        leases = await ps.list_leases(tenant_id=t.id)
        manager_id = ""
        property_id = ""
        if leases:
            property_id = leases[0].property_id
            prop = await ps.get_property(property_id)
            if prop:
                portfolios = await ps.list_portfolios()
                for pf in portfolios:
                    if pf.id == prop.portfolio_id:
                        manager_id = pf.manager_id
                        break

        requests.append(
            EmbeddingRequest(
                id=f"vec:tenant:{t.id}:profile",
                text=text,
                source_entity_id=t.id,
                source_entity_type="Tenant",
                source_field="profile",
                metadata={
                    "manager_id": manager_id,
                    "property_id": property_id,
                    "tenant_name": t.name,
                },
            )
        )
    return requests


async def extract_units(ps: PropertyStore) -> list[EmbeddingRequest]:
    units = await ps.list_units()
    requests: list[EmbeddingRequest] = []

    for u in units:
        prop = await ps.get_property(u.property_id)
        prop_name = prop.name if prop else u.property_id

        parts = [f"Unit {u.unit_number} at {prop_name}"]
        parts.append(f"Status: {u.status.value}")
        if u.bedrooms is not None:
            parts.append(f"{u.bedrooms}BR/{u.bathrooms or '?'}BA")
        if u.sqft:
            parts.append(f"{u.sqft} sqft")
        if u.current_rent > 0:
            parts.append(f"Current rent: {_decimal_str(u.current_rent)}")
        if u.market_rent > 0:
            parts.append(f"Market rent: {_decimal_str(u.market_rent)}")
        if u.days_vacant is not None and u.days_vacant > 0:
            parts.append(f"Vacant {u.days_vacant} days")

        text = ". ".join(parts)
        if len(text.strip()) < 10:
            continue

        manager_id = ""
        if prop:
            portfolios = await ps.list_portfolios()
            for pf in portfolios:
                if pf.id == prop.portfolio_id:
                    manager_id = pf.manager_id
                    break

        requests.append(
            EmbeddingRequest(
                id=f"vec:unit:{u.id}:profile",
                text=text,
                source_entity_id=u.id,
                source_entity_type="Unit",
                source_field="profile",
                metadata={
                    "manager_id": manager_id,
                    "property_id": u.property_id,
                    "property_name": prop_name,
                },
            )
        )
    return requests


async def extract_maintenance(ps: PropertyStore) -> list[EmbeddingRequest]:
    requests_out: list[EmbeddingRequest] = []
    all_requests = await ps.list_maintenance_requests()

    for req in all_requests:
        prop = await ps.get_property(req.property_id)
        prop_name = prop.name if prop else req.property_id

        parts = [f"Maintenance request at {prop_name}, unit {req.unit_id}"]
        if req.title:
            parts.append(f"Title: {req.title}")
        if req.description:
            parts.append(f"Description: {req.description}")
        parts.append(f"Category: {req.category.value}")
        parts.append(f"Priority: {req.priority.value}")
        parts.append(f"Status: {req.status.value}")
        if req.vendor:
            parts.append(f"Vendor: {req.vendor}")
        if req.cost is not None:
            parts.append(f"Cost: {_decimal_str(req.cost)}")

        text = ". ".join(parts)

        manager_id = ""
        if prop:
            portfolios = await ps.list_portfolios()
            for pf in portfolios:
                if pf.id == prop.portfolio_id:
                    manager_id = pf.manager_id
                    break

        requests_out.append(
            EmbeddingRequest(
                id=f"vec:maintenance:{req.id}:description",
                text=text,
                source_entity_id=req.id,
                source_entity_type="MaintenanceRequest",
                source_field="description",
                metadata={
                    "manager_id": manager_id,
                    "property_id": req.property_id,
                    "property_name": prop_name,
                    "priority": req.priority.value,
                    "status": req.status.value,
                },
            )
        )
    return requests_out


async def extract_properties(ps: PropertyStore) -> list[EmbeddingRequest]:
    properties = await ps.list_properties()
    requests: list[EmbeddingRequest] = []

    for p in properties:
        parts = [f"Property: {p.name}"]
        if p.address:
            parts.append(f"Address: {p.address.one_line()}")
        parts.append(f"Type: {p.property_type.value}")
        if p.year_built:
            parts.append(f"Built: {p.year_built}")

        text = ". ".join(parts)

        manager_id = ""
        portfolios = await ps.list_portfolios()
        for pf in portfolios:
            if pf.id == p.portfolio_id:
                manager_id = pf.manager_id
                break

        requests.append(
            EmbeddingRequest(
                id=f"vec:property:{p.id}:profile",
                text=text,
                source_entity_id=p.id,
                source_entity_type="Property",
                source_field="profile",
                metadata={
                    "manager_id": manager_id,
                    "portfolio_id": p.portfolio_id,
                    "property_name": p.name,
                },
            )
        )
    return requests
