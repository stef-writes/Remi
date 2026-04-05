"""API — HTTP delivery layer (FastAPI routers + schemas).

Organized by director capability, not by entity:

    portfolio/       Managers, properties, units, portfolios
    operations/      Leases, maintenance, tenants, actions, notes
    intelligence/    Signals, dashboard, search, ontology, knowledge, events
    system/          Agents, documents, reports, usage, realtime

Cross-cutting modules at root:
    dependencies.py     DI accessors for route handlers
    schemas.py          Entity response types shared across slices
    shared_schemas.py   Common response envelopes (UpdatedResponse, etc.)
"""
