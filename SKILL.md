# REMI — CLI Tool Catalog

> **Real Estate Management Intelligence**
> Every command below is callable by both humans and AI agents. All commands
> support `--json` (or pipe to non-TTY) for structured JSON output.

## Quick Start

```bash
remi --help                      # list all command groups
remi <group> --help              # list commands in a group
remi <group> <command> --help    # show full usage for a command
remi <group> <command> --json    # get structured JSON output
```

---

## Portfolio & Property

| Command | Description |
|---------|-------------|
| `remi portfolio list [--manager M]` | List all portfolios |
| `remi portfolio summary <portfolio_id>` | Portfolio overview: properties, units, occupancy, revenue |
| `remi property list [--portfolio P]` | List properties |
| `remi property inspect <property_id>` | Detailed property inspection with all units |

## Units

| Command | Description |
|---------|-------------|
| `remi units list [--property P] [--status S]` | Search units by property, status, rent range |

## Leases

| Command | Description |
|---------|-------------|
| `remi leases list [--property P] [--status S]` | List leases with optional filters |
| `remi leases expiring [--days N]` | Find leases expiring within N days (default: 60) |

## Tenants

| Command | Description |
|---------|-------------|
| `remi tenants lookup <tenant_id>` | Tenant details and lease history |

## Maintenance

| Command | Description |
|---------|-------------|
| `remi maintenance list [--property P] [--status S]` | List maintenance requests |
| `remi maintenance summary [--property P]` | Counts by status/category, total costs |

## Financial Reports & Metrics

| Command | Description |
|---------|-------------|
| `remi report financial <entity_id> [period] [--type property\|portfolio]` | Financial summary: revenue, expenses, NOI, occupancy |
| `remi report occupancy <entity_id> [--type property\|portfolio]` | Occupancy rate trend over time |
| `remi report rent-analysis [--property P]` | Compare current rents vs market rents |
| `remi report metrics <entity_id> <metric_name> [--type property\|portfolio]` | Query time-series metrics (occupancy_rate, monthly_revenue, maintenance_cost) |

## Documents

| Command | Description |
|---------|-------------|
| `remi documents list` | List uploaded documents with metadata |
| `remi documents query [--doc-id D] [--query Q] [--filters F] [--limit N]` | Search document rows by text, filters, or document ID |

## Knowledge Graph

| Command | Description |
|---------|-------------|
| `remi kb search [--type T] [--query Q] [--namespace N] [--limit N]` | Search entities by type and/or text |
| `remi kb related <entity_id> [--relation-type R] [--direction D] [--max-depth N]` | Find related entities via graph traversal |
| `remi kb summary [--namespace N]` | Entity counts by type, namespace overview |

## Ontology

| Command | Description |
|---------|-------------|
| `remi onto search <type_name> [--filter k=v] [--order-by F] [--limit N]` | Search objects by type with field filters |
| `remi onto get <type_name> <object_id>` | Get a single object by type and ID |
| `remi onto related <object_id> [--link-type T] [--direction D] [--max-depth N]` | Find related objects via link traversal |
| `remi onto aggregate <type_name> <metric> [--field F] [--filter k=v] [--group-by G]` | Compute aggregates (count, sum, avg, min, max) across objects |
| `remi onto timeline <type_name> <object_id> [--event-type E] [--limit N]` | Show event history for an object |
| `remi onto schema [type_name]` | Describe object type properties and links, or list all types |
| `remi onto codify <knowledge_type> [--data k=v] [--source-id S] [--target-id T]` | Codify operational knowledge (observation, policy, causal_link) |
| `remi onto define <type_name> [--description D] [--property name:type]` | Define a new object type to extend the schema |

## AI Agents

| Command | Description |
|---------|-------------|
| `remi ask <app_name> "<question>" [--param key=value]` | Ask an AI agent a question (one-shot) |
| `remi chat` | Interactive multi-turn chat with REMI agents |

## Framework / Internals

| Command | Description |
|---------|-------------|
| `remi app list` | List registered apps |
| `remi app run <path> [--param key=value]` | Run an app by YAML path |
| `remi app inspect <path> <run_id> [--module M]` | Inspect a completed run |
| `remi app info <path>` | Show app graph: nodes, edges, metadata |
| `remi tool list` | List all registered tools |
| `remi tool info <name>` | Describe a tool's parameters and purpose |
| `remi node list <path>` | List nodes in an app graph |
| `remi node inspect <path> <node_id>` | Inspect a node definition |
| `remi provider list` | List available LLM providers |
| `remi serve [--host H] [--port P] [--reload]` | Start the API server |

## Ontology REST API

When the server is running (`remi serve`), the ontology is accessible via HTTP:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ontology/search/{type}` | GET/POST | Search objects of any type |
| `/api/v1/ontology/objects/{type}/{id}` | GET | Get a single object |
| `/api/v1/ontology/related/{id}` | GET | Links and traversal |
| `/api/v1/ontology/aggregate/{type}` | POST | Count, sum, avg, min, max |
| `/api/v1/ontology/timeline/{type}/{id}` | GET | Event history |
| `/api/v1/ontology/schema` | GET | List all types and link types |
| `/api/v1/ontology/schema/{type}` | GET | Describe a single type |
| `/api/v1/ontology/codify` | POST | Codify operational knowledge |
| `/api/v1/ontology/define` | POST | Define a new object type |

The `RemoteOntologyStore` class implements the `OntologyStore` ABC over HTTP
and is a typed, drop-in replacement for `BridgedOntologyStore`. The sandbox
`remi_client.py` module provides a lightweight version for agent scripts.

## Hypothesis REST API

Inductive knowledge discovery — propose, review, and graduate candidate TBox entries:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/hypotheses` | GET | List hypotheses (filter: kind, status, confidence) |
| `/api/v1/hypotheses/{id}` | GET | Get a single hypothesis with evidence |
| `/api/v1/hypotheses/{id}/confirm` | POST | Confirm a hypothesis for graduation |
| `/api/v1/hypotheses/{id}/reject` | POST | Reject a hypothesis |
| `/api/v1/hypotheses/{id}/graduate` | POST | Graduate confirmed → live TBox entry |
| `/api/v1/hypotheses/detect` | POST | Run pattern detector (discover candidates) |
| `/api/v1/hypotheses/graduate-all` | POST | Graduate all confirmed hypotheses |

The `PatternDetector` scans ABox data and produces `Hypothesis` objects (not signals).
The `HypothesisGraduator` promotes confirmed hypotheses into `MutableDomainOntology`,
making them available to the `EntailmentEngine` on the next deductive evaluation run.

---

## JSON Output Contract

Every command with `--json` writes a single JSON object to stdout. Common patterns:

- **List commands**: `{"count": N, "<items>": [...]}`
- **Detail commands**: `{"<entity>_id": "...", ...}`
- **Error responses**: `{"ok": false, "error": "..."}`

## Entity Types

- **property** — A building or complex with units
- **portfolio** — A collection of properties under one manager
- **unit** — An individual rentable unit within a property
- **tenant** — A person or entity occupying a unit
- **lease** — A contract between tenant and property
- **maintenance** — A maintenance/repair request for a unit
- **financial** — Revenue, expense, and NOI data
- **document** — An uploaded CSV/spreadsheet
- **entity** — A knowledge graph node (any of the above)
