"""CLI — Typer command delivery layer.

Organized by director capability:

    portfolio/       managers, property, units, portfolios, rent_roll
    operations/      leases, maintenance, tenants
    intelligence/    dashboard, search, ontology, graph, trace, research
    system/          agents, documents, load, demo, vectors, bench, db

Cross-cutting modules at root:
    shared.py        Container bootstrap, formatting, output helpers
    http.py          HTTP client for sandbox CLI mode
    banner.py        Server startup banner
"""
