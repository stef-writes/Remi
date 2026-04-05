# REMI Architecture

## What This System Is

REMI is an **AI-powered property management platform**. It gives property managers an operational command center backed by an autonomous AI assistant — grounded in real portfolio data and a typed real estate ontology.

A single PM uses REMI to manage their own portfolio: tracking delinquency, vacancies, lease expirations, and maintenance across all properties. As the book of business grows and additional managers come on, the same platform scales into portfolio oversight — comparing managers, rolling up metrics, and surfacing which portfolios need attention.

> **What needs my attention today, and why?**

Under the hood REMI is a layered agent OS — domain ontology, knowledge graph, event system, and LLM runtime — all wired so the agent can reason over real portfolio data.

---

## The Four Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1 — FACTS (Storage Adapters)                              │
│                                                                  │
│  PropertyStore: properties, units, leases, tenants, maintenance  │
│  KnowledgeStore: relationships, graph entities, observations     │
│  ContentStore: raw document content (rows, chunks, text)         │
│  SignalStore, VectorStore, TraceStore, MemoryStore, ChatStore    │
│  EventStore: domain change events (ChangeSet)                    │
│                                                                  │
│  What actually happened. No interpretation.                      │
│  Postgres adapters available for persistent storage.             │
└────────────────────────┬─────────────────────────────────────────┘
                         │ interpreted through
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 2 — DOMAIN (TBox + Ontology + Settings)                   │
│                                                                  │
│  domain.yaml: signal definitions, thresholds, policies,          │
│    causal chains, compositions, workflows                        │
│  Ontology: object types, link types, constraints                 │
│  Container: dependency injection, wires everything together      │
│  Settings: environment config (Pydantic)                         │
│                                                                  │
│  What things mean in this business. Domain expertise formalized. │
│  Editable by domain experts without touching code.               │
└────────────────────────┬─────────────────────────────────────────┘
                         │ used by
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 3 — SERVICES                                              │
│                                                                  │
│  Domain Services                                                 │
│    DashboardQueryService — computes portfolio operational state  │
│    ManagerReviewService — manager performance analysis           │
│    DocumentIngestService — report ingestion pipeline             │
│    Portfolio, RentRoll, AutoAssign query services                │
│    EmbeddingPipeline — vector search over entities + documents   │
│    SearchService — semantic search across the knowledge base     │
│    PortfolioLoader — bulk ingest from report directories         │
│                                                                  │
│  The agent reasons over data via tools that call these services. │
│  No precomputed signal engine — the agent queries on demand.     │
└────────────────────────┬─────────────────────────────────────────┘
                         │ consumed by
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 4 — INTERFACES                                            │
│                                                                  │
│  4A — REST API (FastAPI)                                         │
│    Routers under /api/v1, organized by capability:               │
│    portfolio/    — managers, properties, units, portfolios        │
│    operations/   — leases, maintenance, tenants, actions, notes  │
│    intelligence/ — signals, dashboard, search, ontology,         │
│                    knowledge, events                              │
│    system/       — agents, documents, reports, usage, realtime    │
│                                                                  │
│  4B — Agent Chat (REST Streaming)                                │
│    POST /api/v1/agents/{name}/ask — NDJSON streaming             │
│    (delta, tool_call, tool_result, done events)                  │
│                                                                  │
│  4C — WebSocket (Events Only)                                    │
│    /ws/events — real-time lifecycle events                        │
│                                                                  │
│  4D — CLI (Typer)                                                │
│    portfolio/    — managers, property, units, portfolios,         │
│                    rent_roll (report)                             │
│    operations/   — leases, maintenance, tenants                  │
│    intelligence/ — dashboard, search, onto, graph, trace,        │
│                    research                                       │
│    system/       — ai, documents, load, demo, vectors, bench, db │
│                                                                  │
│  4E — Frontend (Next.js 16 + React 19)                           │
│    Command center, Ask (chat), Delinquency, Vacancies, Leases,   │
│    Documents, Property detail, Manager detail                    │
│                                                                  │
│  4F — LLM Agents                                                 │
│    Director: fast Q&A, 1-5 tool calls, structured data queries   │
│    Researcher: deep analysis, sandbox Python, up to 30 iters     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Three Kinds of Knowledge

### Domain TBox

The **DomainTBox** defines what things mean in this business. It is institutional expertise formalized. It contains:

- **Signal definitions** — named domain states with descriptions, severity, entity scope, and evaluation rules
- **Thresholds** — numeric calibrations (vacancy_chronic_days: 30, delinquency_critical_pct: 0.08, etc.)
- **Policies** — deontic obligations (late fee grace, 3-day notice, emergency response, renewal offers, make-ready deadlines)
- **Causal chains** — known cause-effect relationships (slow maintenance → extended vacancy)
- **Compositions** — compound signals from co-occurring constituents (DelinquencyLeaseCliff, OperationalBreakdown, DecliningPortfolio)
- **Workflows** — operational step sequences (turnover, collections, maintenance)

Lives in `src/remi/shell/config/domain.yaml`. No code change required to update a threshold or add a signal definition.

### Ontology

The **Ontology** defines what types of things exist and how they relate. Object types (Property, Unit, Lease, Tenant), link types (BELONGS_TO, COVERS, CAUSES), and their constraints. Small, stable, loaded at boot.

Implemented in `src/remi/application/infra/ontology/`. The `BridgedKnowledgeGraph` routes core type queries to `PropertyStore` and non-core/graph queries to `KnowledgeStore`.

### Knowledge Graph

The **KnowledgeGraph** stores individual facts about the world. Properties, units, leases, tenants, maintenance requests, uploaded report data, codified observations.

Populated by the ingestion pipeline from uploaded reports (rule-based extraction first, LLM fallback second).

---

## The LLM's Role

The LLM is the reasoning engine. It has the full domain ontology as context (TBox) and can query the knowledge graph through tools. It does not rely on precomputed signals — it queries data on demand and reasons about what it finds.

The LLM contributes:
1. **Reading unstructured text** — delinquency notes, maintenance descriptions, tenant histories
2. **Connecting patterns** — a maintenance backlog and vacancy duration on the same portfolio are probably related
3. **Recommending action** — not just "there is a problem" but specific next steps
4. **Data science** — statistical analysis via sandbox code execution (researcher agent)
5. **Translating to human language** — users read prose, not JSON
6. **On-demand analysis** — "show me properties with delinquency above 8%" is a tool call, not a precomputed label

---

## Sandbox

The researcher agent has access to an isolated Python sandbox for data analysis.

- Each session gets its own temp directory
- Python runs in a subprocess (no host filesystem access)
- Pre-loaded with portfolio data as CSVs (managers, portfolios, properties, units, leases, tenants, maintenance)
- Analytics dependencies available: pandas, numpy, scipy, scikit-learn, statsmodels

---

## Ingestion Pipeline

Reports enter the system through `src/remi/application/services/ingestion/`.
The pipeline uses **two tiers**: a deterministic rule-based extractor first
(zero API calls), and an LLM fallback for unknown formats.

### Two Tiers

**Tier 1 — Rule-based** (`rules.py`): Detects report type from column-header
signatures, maps columns to entity fields via static dictionaries, filters
junk rows (section headers, internal bookkeeping entries), and normalizes
addresses. Handles all four standard AppFolio report types. ~1ms per report.

**Tier 2 — LLM fallback** (`service.py` → `agent/pipeline/`): Three-stage
YAML pipeline (classify → extract → enrich) with ontology schemas injected
as context. Used only when the rule engine can't match the columns.

Both tiers converge at the same `resolve_and_persist` path.

### Key modules

| Module | Role |
|--------|------|
| `pipeline.py` | `DocumentIngestService` — upload → parse → rules/LLM extract → persist → embed |
| `rules.py` | Deterministic column-mapping extractor — detects report type, maps fields, filters junk |
| `service.py` | `IngestionService` — drives LLM pipeline (fallback) or persists pre-mapped rows (rule path) |
| `persist.py` | `resolve_and_persist` — maps extracted rows to domain models and writes to PropertyStore + KnowledgeStore |
| `managers.py` | `ManagerResolver` — frequency-based manager classification, deduplication |

---

## Trace Layer

Every reasoning step is captured as a **Span** in a hierarchical **Trace** (`src/remi/agent/observe/`).

Span kinds: `PERCEPTION`, `LLM_CALL`, `TOOL_CALL`, `REASONING`, `SIGNAL`, `GRAPH`, `MODULE`.

Agents have access to `trace_list`, `trace_show`, and `trace_spans` tools for metacognitive inspection. Every structlog event automatically includes `trace_id` and `span_id` when a trace is active.

---

## Provenance Tags

Every fact and observation carries a provenance tag:

| Tag | Meaning | Trust |
|-----|---------|-------|
| `CORE` | Defined by the system at build time | Highest |
| `SEEDED` | Loaded at bootstrap from domain.yaml | High |
| `DATA_DERIVED` | Computed from knowledge graph facts | High |
| `USER_STATED` | Asserted by the user | High (overridable) |
| `INFERRED` | Produced by the LLM via reasoning | Medium (verify) |

---

## Key Files

| File | Role |
|------|------|
| `src/remi/shell/config/domain.yaml` | Source of truth — signal definitions, thresholds, policies, causal chains, workflows |
| `src/remi/shell/config/container.py` | DI container — wires all stores, services, agents, tools |
| `src/remi/shell/config/__init__.py` | Settings (Pydantic) |
| `src/remi/application/agents/director/app.yaml` | Director agent — fast Q&A, system prompt, tool set |
| `src/remi/application/agents/researcher/app.yaml` | Researcher agent — deep analysis, sandbox, phased protocol |
| `src/remi/agent/runtime/` | AgentNode — config-driven think-act-observe loop |
| `src/remi/agent/context/` | Assembles agent context from knowledge graph + signals |
| `src/remi/agent/graph/` | Knowledge graph types, bridge, retriever |
| `src/remi/application/services/queries/dashboard.py` | Computes portfolio operational state |
| `src/remi/application/services/ingestion/rules.py` | Rule-based report extraction — deterministic, zero-LLM |
| `src/remi/application/services/ingestion/pipeline.py` | Document ingestion orchestrator (rules first, LLM fallback) |
| `src/remi/application/tools/__init__.py` | Tool registration — wires all tool groups |
| `src/remi/shell/api/main.py` | FastAPI app factory, lifespan, router attachment |
| `src/remi/shell/cli/main.py` | CLI entry point — all command groups |
