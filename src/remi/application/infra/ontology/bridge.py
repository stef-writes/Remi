"""RE-specific wiring of PropertyStore into a BridgedKnowledgeGraph.

This is the real-estate factory — maps entity repos to core_types bindings
and configures the generic GraphProjector with RE-specific FK mappings.
"""

from __future__ import annotations

from remi.agent.graph import (
    BridgedKnowledgeGraph,
    CoreTypeBindings,
    GraphProjector,
    KnowledgeStore,
)
from remi.application.core.protocols import PropertyStore
from remi.application.infra.ontology.schema import FK_PROJECTION_MAP


def build_knowledge_graph(
    property_store: PropertyStore,
    knowledge_store: KnowledgeStore,
) -> tuple[BridgedKnowledgeGraph, GraphProjector]:
    """Factory: wire REMI's PropertyStore methods into a BridgedKnowledgeGraph.

    Returns both the graph and a projector configured with RE FK mappings.
    """
    ps = property_store
    core_types: CoreTypeBindings = {
        "PropertyManager": (ps.get_manager, ps.list_managers),
        "Portfolio": (ps.get_portfolio, ps.list_portfolios),
        "Property": (ps.get_property, ps.list_properties),
        "Unit": (ps.get_unit, ps.list_units),
        "Lease": (ps.get_lease, ps.list_leases),
        "Tenant": (ps.get_tenant, ps.list_tenants),
        "MaintenanceRequest": (ps.get_maintenance_request, ps.list_maintenance_requests),
        "ActionItem": (ps.get_action_item, ps.list_action_items),
        "Owner": (ps.get_owner, ps.list_owners),
        "Vendor": (ps.get_vendor, ps.list_vendors),
        "Note": (ps.get_note, ps.list_notes),
        "Document": (ps.get_document, ps.list_documents),
    }
    kg = BridgedKnowledgeGraph(knowledge_store, core_types=core_types)
    projector = GraphProjector(kg, FK_PROJECTION_MAP)
    return kg, projector
