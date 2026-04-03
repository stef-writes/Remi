# REMI Architecture

## What This System Is

REMI is an **agent operating system** for directors of property management. A director oversees multiple property managers, each running portfolios of 15-40 properties. Her job is not to manage properties — it is to manage managers. Her core question, every day, is:

> **Which of my managers needs my attention, and why?**

REMI answers that question before she asks it. To the director it feels like a PM dashboard with a very capable autonomous assistant. Under the hood it is a layered agent OS — domain ontology, signal engine, knowledge graph, and LLM runtime — all wired so the agent can reason over real portfolio data. It monitors the book of business, detects situations that require the director's judgment, and provides an AI agent that can explain, investigate, and recommend — grounded in actual data and domain expertise.

---

## The Four Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1 — FACTS (Storage Adapters)                              │
│                                                                  │
│  PropertyStore: properties, units, leases, tenants, maintenance  │
│  KnowledgeStore: relationships, graph entities, observations     │
│  DocumentStore: uploaded AppFolio reports (raw rows)             │
│  SignalStore, VectorStore, TraceStore, MemoryStore, ChatStore    │
│  SnapshotStore: point-in-time metric snapshots                   │
│                                                                  │
│  What actually happened. No interpretation.                      │
│  Postgres adapters available for persistent storage.             │
└────────────────────────┬─────────────────────────────────────────┘
                         │ evaluated against
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 2 — DOMAIN (TBox + Ontology + Settings)               │
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
                         │ produces
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 3 — SIGNALS & SERVICES                                    │
│                                                                  │
│  Entailment Engine                                               │
│    CompositeProducer merges:                                     │
│      ├── RuleBasedProducer — evaluates domain.yaml rules         │
│      │   Evaluators: existence, threshold, trend, delinquency,   │
│      │   lease, maintenance, portfolio, composition               │
│      └── StatisticalProducer — z-score outliers, concentrations  │
│                                                                  │
│  Domain Services                                                 │
│    DashboardQueryService — computes director dashboard state     │
│    ManagerReviewService — manager performance review             │
│    DocumentIngestService — report ingestion pipeline             │
│    Lease, Portfolio, Property, Maintenance query services        │
│    RentRollService, SnapshotService, AutoAssignService           │
└────────────────────────┬─────────────────────────────────────────┘
                         │ consumed by
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 4 — INTERFACES                                            │
│                                                                  │
│  4A — REST API (FastAPI)                                         │
│    17 routers under /api/v1 — dashboard, signals, managers,      │
│    portfolios, properties, units, leases, maintenance, tenants,  │
│    documents, ontology, agents, seed, actions, notes             │
│                                                                  │
│  4B — WebSocket                                                  │
│    /ws/chat — streaming agent chat                               │
│    /ws/events — real-time signal/ingestion events                │
│                                                                  │
│  4C — CLI (Typer)                                                │
│    remi serve, dashboard, ai, research, onto, portfolio,         │
│    property, units, leases, maintenance, tenants, report,        │
│    documents, trace, seed, bench                                 │
│                                                                  │
│  4D — Frontend (Next.js 16 + React 19)                           │
│    Dashboard, Ask (chat), Delinquency, Vacancies, Leases,        │
│    Documents, Performance, Property detail, Manager detail        │
│                                                                  │
│  4E — LLM Agents                                                 │
│    Director: fast Q&A, 1-5 tool calls, structured data queries   │
│    Researcher: deep analysis, sandbox Python, up to 30 iters     │
│    + internal agents (action planner, report classifier,          │
│      knowledge enricher)                                          │
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

Lives in `src/remi/config/domain.yaml`. No code change required to update a threshold or add a signal.

### Ontology

The **Ontology** defines what types of things exist and how they relate. Object types (Property, Unit, Lease, Tenant), link types (BELONGS_TO, COVERS, CAUSES), and their constraints. Small, stable, loaded at boot.

Implemented in `src/remi/knowledge/ontology/`. The `BridgedKnowledgeGraph` routes core type queries to `PropertyStore` and non-core/graph queries to `KnowledgeStore`.

### Knowledge Graph

The **KnowledgeGraph** stores individual facts about the world. Properties, units, leases, tenants, maintenance requests, uploaded report data, codified observations.

Populated by the ingestion pipeline from AppFolio report exports.

---

## Entailment Engine

The entailment engine is the core reasoning system. It evaluates domain.yaml rules against knowledge graph facts and produces Signals.

### Evaluators

Each signal type has a specialized evaluator in `src/remi/knowledge/entailment/`:

| Evaluator | What It Checks |
|-----------|---------------|
| `ExistenceEvaluator` | Whether a condition exists (CommunicationGap) |
| `ThresholdEvaluator` | Metric exceeds/below a numeric threshold |
| `TrendEvaluator` | Metrics moving in a consistent direction over periods |
| `DelinquencyEvaluator` | Delinquency-specific rate and pattern analysis |
| `LeaseEvaluator` | Lease expiration concentration |
| `MaintenanceEvaluator` | Work order aging |
| `PortfolioEvaluator` | Portfolio-level metric analysis |
| `CompositionEvaluator` | Co-occurring constituent signals |

### Signal Lifecycle

1. Data enters the knowledge graph (ingestion or user assertion)
2. `SignalPipeline.run_all()` triggers all evaluators
3. Each evaluator checks its rules against current facts
4. Signals produced with evidence, severity, provenance
5. Stored in `SignalStore`
6. Compositions evaluated against existing signals

---

## The LLM's Role

The LLM does **not** detect signals. The entailment engine does that. The LLM's job is **abductive reasoning** — inference to the best explanation.

```
Deduction  →  EntailmentEngine    →  "There IS a LeaseExpirationCliff"
                                     (certain, rule-based, pre-computed)

Abduction  →  LLM                 →  "The cliff is likely unmanaged because
                                     three of the five expiring tenants have
                                     been month-to-month for 2+ years"
                                     (probable, context-dependent)
```

The LLM contributes:
1. **Reading unstructured text** — delinquency notes, maintenance descriptions, tenant histories
2. **Connecting signals** — a maintenance backlog and vacancy duration on the same portfolio are probably related
3. **Recommending action** — not just "there is a problem" but specific next steps
4. **Data science** — statistical analysis via sandbox code execution (researcher agent)
5. **Translating to human language** — the director reads prose, not JSON

---

## Sandbox

The researcher agent has access to an isolated Python sandbox for data analysis.

- Each session gets its own temp directory
- Python runs in a subprocess (no host filesystem access)
- Pre-seeded with portfolio data as CSVs (managers, portfolios, properties, units, leases, tenants, maintenance, signals)
- Analytics dependencies available: pandas, numpy, scipy, scikit-learn, statsmodels
- `SandboxSeeder` exports `PropertyStore` + `SignalStore` data at session start

---

## Ingestion Pipeline

Reports enter the system through `src/remi/knowledge/ingestion/`. Ingestion
is **schema-driven**: each report type is a declarative `ReportSchema` in
`schema.py` — adding a new report type means adding a schema definition,
not a new handler file.

### Two categories of report

| Category | Report Types | What It Does |
|----------|-------------|--------------|
| **Migration** | Property Directory | Creates managers and properties. Runs once (or rarely). Uses frequency-based classification to distinguish real manager names from operational tags. |
| **Recurring** | Delinquency, Rent Roll, Lease Expiration | Creates/updates units, tenants, leases. Never creates managers — looks up existing property-to-portfolio mapping. |

Unknown report types fall back to generic ingestion (raw rows stored as KB entities for later enrichment).

### Key modules

| Module | Role |
|--------|------|
| `schema.py` | `ReportSchema` definitions + unified `ingest_report()` loop |
| `managers.py` | Frequency-based manager classification + `ManagerResolver` |
| `service.py` | `IngestionService` — report type detection + schema dispatch |
| `generic.py` | Fallback for unrecognized report types |
| `helpers.py` | Address parsing, occupancy mapping |

Report type detection uses scored column fingerprinting (`appfolio_schema.py`),
with LLM classification as fallback for unknown layouts.

---

## Trace Layer

Every reasoning step is captured as a **Span** in a hierarchical **Trace** (`src/remi/observability/tracer.py`).

Span kinds: `ENTAILMENT`, `PERCEPTION`, `LLM_CALL`, `TOOL_CALL`, `REASONING`, `SIGNAL`, `GRAPH`, `MODULE`.

Agents have access to `trace_list`, `trace_show`, and `trace_spans` tools for metacognitive inspection. Every structlog event automatically includes `trace_id` and `span_id` when a trace is active.

---

## Provenance Tags

Every fact, signal, and observation carries a provenance tag:

| Tag | Meaning | Trust |
|-----|---------|-------|
| `CORE` | Defined by the system at build time | Highest |
| `SEEDED` | Loaded at bootstrap from domain.yaml | High |
| `DATA_DERIVED` | Computed from knowledge graph facts by entailment | High |
| `USER_STATED` | Asserted by the director or a manager | High (overridable) |
| `INFERRED` | Produced by the LLM via abductive reasoning | Medium (verify) |

---

## Key Files

| File | Role |
|------|------|
| `src/remi/config/domain.yaml` | Source of truth — signals, thresholds, policies, causal chains, workflows |
| `src/remi/config/container.py` | DI container — wires all stores, services, agents, tools |
| `src/remi/config/settings.py` | Environment configuration (Pydantic settings) |
| `src/remi/agents/director/app.yaml` | Director agent — fast Q&A, system prompt, tool set |
| `src/remi/agents/researcher/app.yaml` | Researcher agent — deep analysis, sandbox, phased protocol |
| `src/remi/agent/node.py` | AgentNode — config-driven think-act-observe loop |
| `src/remi/knowledge/entailment/engine.py` | Entailment engine — evaluates rules, produces signals |
| `src/remi/knowledge/context_builder.py` | Assembles agent context from knowledge graph + signals |
| `src/remi/knowledge/graph_retriever.py` | Retrieves entities and relationships from the graph |
| `src/remi/services/dashboard.py` | Computes director dashboard state from signals |
| `src/remi/services/manager_review.py` | Manager performance review logic |
| `src/remi/tools/__init__.py` | Tool registration — wires all tool groups |
| `src/remi/api/main.py` | FastAPI app factory, lifespan, router attachment |
| `src/remi/cli/main.py` | CLI entry point — all command groups |
