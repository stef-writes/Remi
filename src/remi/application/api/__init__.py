"""API — HTTP delivery layer (FastAPI routers + schemas).

    dependencies.py     DI accessors for route handlers
    shared_schemas.py   Shared response types (UpdatedResponse, DeletedResponse, etc.)

    One module per resource: properties, units, leases, tenants, managers,
    portfolios, maintenance, actions, dashboard, documents, ontology, signals,
    search, seed, agents, usage, realtime.
"""
