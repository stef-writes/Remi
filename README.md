# REMI — Real Estate Management Intelligence

An agent operating system for directors of property management. REMI is the runtime that lets an AI agent monitor the book of business, detect situations that require the director's judgment, and autonomously explain, investigate, and recommend — grounded in actual portfolio data and a typed real estate ontology.

To the director it feels like a capable autonomous assistant sitting beside them. Under the hood it is a layered agent OS: domain ontology, signal engine, knowledge graph, and LLM runtime — all wired together so the agent can reason over real data.

The director's core question: **which of my managers needs my attention, and why?**

## Quick Start

```bash
# Install with dev dependencies
uv sync --extra dev

# Start the API server (seed from AppFolio reports)
uv run remi serve --seed

# Start the frontend (separate terminal)
cd frontend && npm install && npm run dev

# Open http://localhost:3000
```

### CLI Examples

```bash
uv run remi onto signals              # Active signals across the portfolio
uv run remi onto explain <signal-id>  # Evidence behind a signal
uv run remi onto search Property      # Search entities by type
uv run remi dashboard                 # Textual TUI dashboard
uv run remi ai ask "How is Marcus doing?"  # Ask the director agent
uv run remi research "Seasonal vacancy patterns across the portfolio"
uv run remi trace list                # Recent reasoning traces
```

## Architecture

REMI is an agent operating system built on four packages. Each has a single job. The directory tree *is* the architecture — an LLM navigating the codebase can infer what exists from `ls` alone.

```
src/remi/
  agent/       AI infrastructure — LLM runtime, signals, graph, vectors, sandbox, documents, tracing
  domain/      Real estate product — portfolio models, queries, evaluators, ingestion, ontology, search, tools
  types/       Shared vocabulary — ids, clock, errors, enums, result, text
  shell/       Composition root — DI container, settings, API, CLI
```

Dependency direction: `domain/` imports from `agent/` — never the reverse. `shell/` wires both. `types/` imports nothing.

The `Container` (in `shell/config/container.py`) is pure wiring — it calls factory functions defined in the modules that own the things being built.

**Key constraint:** The LLM agent does NOT detect signals — the entailment engine does. The LLM explains, connects, recommends, and codifies.

### Three Kinds of Knowledge

| Layer | What | Where |
|-------|------|-------|
| **Domain TBox** | What things mean — signal definitions, thresholds, policies, causal chains | `shell/config/domain.yaml` |
| **Ontology** | What entity types exist and how they relate — typed properties, structural links, constraints | `domain/ontology/schema.py` |
| **Knowledge Graph** | What actually happened — entities, relationships, observations | `PropertyStore` + `KnowledgeStore` via `BridgedKnowledgeGraph` |

The **Entailment Engine** evaluates TBox rules against knowledge graph facts and produces **Signals** — named, evidenced, severity-ranked domain states.

## The Twelve Signals

Defined in `domain.yaml`, detected by the entailment engine.

### Portfolio Health

| Signal | What It Means |
|--------|---------------|
| `OccupancyDrift` | Occupancy declining over 2+ consecutive periods |
| `DelinquencyConcentration` | Delinquency rate exceeds threshold of gross rent roll |
| `LeaseExpirationCliff` | >30% of leases expire within 60 days with no renewals underway |
| `VacancyDuration` | Units vacant beyond 30 days (market-normal window) |
| `MaintenanceBacklog` | Open work orders aging without resolution |

### Manager Performance

| Signal | What It Means |
|--------|---------------|
| `OutlierPerformance` | Manager significantly below peer group on key metrics |
| `PerformanceTrend` | Manager metrics moving in a consistent direction over recent periods |
| `CommunicationGap` | Situations visible in data that the director hasn't been told about |

### Operational

| Signal | What It Means |
|--------|---------------|
| `PolicyBreach` | Required action didn't happen within prescribed timeline |
| `LegalEscalationRisk` | Tenant situation approaching or in a legal track |
| `BelowMarketRent` | Units significantly below market rent, no renewal planned |
| `ConcentrationRisk` | Single property/tenant type is too large a share of a portfolio |

### Compositions (compound signals)

| Signal | Constituents | Severity |
|--------|-------------|----------|
| `DelinquencyLeaseCliff` | DelinquencyConcentration + LeaseExpirationCliff | Critical |
| `OperationalBreakdown` | PolicyBreach + CommunicationGap | Critical |
| `DecliningPortfolio` | OccupancyDrift + OutlierPerformance | High |

## Agents

Two conversational agents, declared via YAML in `domain/agents/`.

| Agent | Purpose | Mode |
|-------|---------|------|
| **Director** (`director/app.yaml`) | Fast Q&A analyst — answers questions using structured data queries and signal awareness. 1-5 tool calls per turn. | Chat |
| **Researcher** (`researcher/app.yaml`) | Deep analytical engine — loads portfolio into DataFrames, runs statistical analysis (regression, clustering, anomaly detection), produces structured research reports. Up to 30 iterations. | Chat |

Internal agents (not user-facing):

| Agent | Purpose |
|-------|---------|
| **Action Planner** (`action_planner/app.yaml`) | Sub-agent that produces structured JSON action plans |

## Tools

Tools registered in `domain/tools/`, available to agents:

### Knowledge Graph (12 tools)

`onto_signals`, `onto_explain`, `onto_search`, `onto_get`, `onto_related`, `onto_aggregate`, `onto_timeline`, `onto_schema`, `onto_codify_observation`, `onto_codify_policy`, `onto_codify_causal_link`, `onto_define_type`

### Workflows (5 tools)

`portfolio_review`, `delinquency_review`, `lease_risk_review`, `draft_action_plan`, `approve_action_plan`

### Documents (2 tools)

`document_list`, `document_query`

### Sandbox (5 tools)

`sandbox_exec`, `sandbox_exec_python`, `sandbox_write_file`, `sandbox_read_file`, `sandbox_list_files`

### Vectors (2 tools)

`semantic_search`, `vector_stats`

### Actions (4 tools)

`action_create`, `action_update`, `action_list`, `note_create`

### Trace (3 tools)

`trace_list`, `trace_show`, `trace_spans`

### Memory (2 tools)

`memory_store`, `memory_recall`

## API

`uv run remi serve` starts FastAPI on `http://127.0.0.1:8000`. All REST routes are prefixed `/api/v1`.

| Group | Prefix | Key Routes |
|-------|--------|------------|
| Dashboard | `/dashboard` | `GET /overview`, `/delinquency`, `/leases/expiring`, `/vacancies`, `/rent-roll/{id}`, `/needs-manager`, `/snapshots`, `/metrics-history`, `POST /snapshots/capture`, `/auto-assign` |
| Signals | `/signals` | `GET /`, `/{id}`, `/{id}/explain`, `POST /infer`, `/{id}/feedback` |
| Managers | `/managers` | `GET /`, `/{id}/review`, `POST /`, `PATCH /{id}`, `DELETE /{id}`, `POST /merge`, `/{id}/assign` |
| Portfolios | `/portfolios` | `GET /`, `/{id}`, `/{id}/summary` |
| Properties | `/properties` | `GET /`, `/{id}`, `/{id}/units`, `/{id}/rent-roll`, `PATCH /{id}`, `DELETE /{id}` |
| Units | `/units` | `GET /` |
| Leases | `/leases` | `GET /`, `/expiring` |
| Maintenance | `/maintenance` | `GET /`, `/summary` |
| Tenants | `/tenants` | `GET /{id}`, `PATCH /{id}`, `DELETE /{id}` |
| Documents | `/documents` | `POST /upload`, `GET /`, `/{id}`, `/{id}/rows`, `DELETE /{id}` |
| Ontology | `/ontology` | `GET|POST /search/{type}`, `/objects/{type}/{id}`, `/related/{id}`, `POST /aggregate/{type}`, `GET /timeline/{type}/{id}`, `/schema`, `POST /codify`, `/define` |
| Actions | `/actions` | CRUD for action items and notes |
| Notes | `/notes` | CRUD for standalone notes |
| Agents | `/agents` | `GET /models`, `GET /` |
| Seed | `/seed` | `POST /reports`, `POST /demo` |

### WebSocket

| Endpoint | Purpose |
|----------|---------|
| `ws://localhost:8000/ws/chat` | Streaming chat with the director/researcher agent |
| `ws://localhost:8000/ws/events` | Real-time server-sent events (signal updates, ingestion progress) |

### Health

`GET /health` — status, version, uptime, trace/span counts.

## Frontend

Next.js 16 app with React 19, Tailwind 4, and Framer Motion. Connects to the API server.

**Pages** (under `frontend/src/app/(shell)/`):

| Route | Page |
|-------|------|
| `/` | Home |
| `/dashboard` | Director dashboard — signals, portfolio overview |
| `/ask` | Chat interface — talk to the director or researcher agent |
| `/delinquency` | Delinquency analysis |
| `/vacancies` | Vacancy tracking |
| `/leases` | Lease expiration analysis |
| `/documents` | Document upload and management |
| `/performance` | Manager performance comparison |
| `/properties/[id]` | Property detail view |
| `/managers/[id]` | Manager detail view |

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

## CLI Reference

| Command | Purpose |
|---------|---------|
| `remi serve [--seed]` | Start the API server (optionally ingest AppFolio reports) |
| `remi dashboard` | Textual TUI dashboard |
| `remi ai ask <question>` | Ask the director agent |
| `remi research <question>` | Deep research with the researcher agent |
| `remi onto signals` | List active entailed signals |
| `remi onto explain <id>` | Evidence behind a signal |
| `remi onto search <type>` | Search entities by type |
| `remi onto get <id>` | Get a single entity |
| `remi onto related <id>` | Traverse entity relationships |
| `remi onto aggregate <type>` | Aggregate metrics |
| `remi onto timeline <type> <id>` | Temporal events for an entity |
| `remi onto schema` | Inspect ontology schema |
| `remi onto codify <kind> ...` | Assert an observation, policy, or causal link |
| `remi onto define <type>` | Define a new entity type |
| `remi onto infer` | Re-evaluate all rules against current facts |
| `remi portfolio list` | List portfolios |
| `remi portfolio summary <id>` | Portfolio summary |
| `remi property list` | List properties |
| `remi property inspect <id>` | Property details |
| `remi units list` | List units |
| `remi leases list` | List leases |
| `remi leases expiring` | Expiring leases |
| `remi maintenance list` | List maintenance requests |
| `remi maintenance summary` | Maintenance summary |
| `remi tenants lookup <id>` | Tenant lookup |
| `remi report rent-analysis` | Rent analysis report |
| `remi documents list` | List uploaded documents |
| `remi documents query` | Query document rows |
| `remi trace list` | Recent traces |
| `remi trace show <id>` | Full span tree |
| `remi trace spans <id>` | Flat span list |
| `remi seed` | Ingest AppFolio report exports |
| `remi bench` | Run benchmarks |

## Module Map

```
src/remi/

── agent/           AI infrastructure — the agent operating system kernel
  llm/              LLM provider ports + adapters (Anthropic, OpenAI, Gemini)
  vectors/          Embedding ports + adapters
  sandbox/          Code execution ports + adapters (local, Docker)
  observe/          Structured logging (structlog), tracing
  signals/          Signal framework — types, stores, producers, pattern mining
  graph/            Knowledge graph — types, bridge, retriever
  documents/        Document types, stores, parsers
  db/               Database engine + table metadata
  runtime/          LLM execution loop, tool dispatch, streaming
  context/          Perception, context builder, intent classification
  conversation/     Thread management, compression
  ingestion/        Generic LLM pipeline runner (YAML-driven steps)
  tools/            Domain-agnostic tools (sandbox, vectors, memory, trace)

── domain/          Real estate product intelligence
  portfolio/        Entity DTOs (Property, Unit, Tenant, Lease, etc.), protocols, business rules
  stores/           RE persistence adapters (in-memory, Postgres)
  queries/          RE query services (dashboard, rent roll, leases, maintenance, etc.)
  evaluators/       RE signal producers (delinquency, lease, maintenance, portfolio, etc.)
  ingestion/        RE inbound data pipeline — ontology-driven resolver
    resolver.py     Schema-driven: LLM rows → domain models → PropertyStore + KnowledgeStore
    service.py      IngestionService — orchestrates LLM pipeline + resolver
    pipeline.py     DocumentIngestService — upload → parse → ingest → signal → embed
    managers.py     Frequency-based manager classification + ManagerResolver
    seed.py         Batch ingestion of sample report exports
    embedding.py    Post-ingestion embedding pipeline
    validation.py   Row-level validation
    adapters/       Platform-specific schema hints (AppFolio)
  ontology/         RE knowledge graph schema — entity types, structural links
  search/           RE-aware hybrid search + pattern detection
  tools/            RE agent capabilities (register_all_tools)
  configs/          RE agent YAML manifests (director, researcher, action_planner, document_ingestion)

── types/           Shared vocabulary — ids, clock, errors, enums, result, text

── shell/           Composition root
  config/           DI container, settings, domain.yaml
  api/              FastAPI routers, schemas, middleware, WebSocket
  cli/              Typer CLI entry points
```

## Data Ingestion

REMI ingests property management report exports (XLSX/CSV). Ingestion is **ontology-driven** — the domain ontology in `domain/ontology/schema.py` defines entity types and their fields, and the LLM extraction pipeline uses this schema directly in its prompts.

### Pipeline

1. Upload via `POST /api/v1/documents/upload` or `remi seed`
2. Three-step LLM pipeline (classify → extract → enrich) with ontology schemas injected as context
3. Schema-driven resolver maps extracted rows directly to typed domain models (no intermediate event layer)
4. Domain models persisted to PropertyStore + mirrored to KnowledgeStore
5. Performance snapshot captured
6. Entailment engine runs — produces signals
7. Pattern detector runs — proposes hypotheses
8. Embedding pipeline runs — enables semantic search

### Report categories

| Category | Reports | Creates Managers? |
|----------|---------|-------------------|
| **Migration** | Property Directory | Yes — frequency-based classification separates real managers from operational tags |
| **Recurring** | Delinquency, Rent Roll, Lease Expiration, Work Orders | No — consumes existing property-to-portfolio mappings |

`AutoAssignService` assigns unassigned properties to *existing* managers only — it never creates new ones.

## LLM Providers

Default provider is Anthropic (Claude). Additional providers available as optional dependencies:

```bash
uv sync --extra openai       # OpenAI
uv sync --extra gemini       # Google Gemini
uv sync --extra all-providers # All three
```

Configure via environment variables or settings:

```bash
export ANTHROPIC_API_KEY=sk-...
export REMI_LLM__DEFAULT_PROVIDER=anthropic
export REMI_LLM__DEFAULT_MODEL=claude-sonnet-4-20250514
```

## Development

```bash
# Run tests
uv run pytest tests/ -q

# Run specific test folder
uv run pytest tests/entailment/ -q

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/

# Format
uv run ruff format src/ tests/
```

## Project Conventions

- Always use `uv run` to execute Python — never `python` directly
- Always use `uv add` for dependencies — never `pip install`
- Use `structlog` for logging — not `print()` or stdlib `logging`
- Never silently swallow errors — let them raise
- Never use `typing.TYPE_CHECKING` — if you need it, the dependency is in the wrong place
- `domain.yaml` is the source of truth for signals, thresholds, and rules — do not hardcode these in Python
- `types/` is for cross-cutting primitives only — no business logic
- Factory functions live in the module that defines the thing being built, not in the container
- New code depends on the narrowest repository protocol (`LeaseRepository`, not `PropertyStore`)
- Backward-compat aliases get a `# COMPAT:` comment

## License

MIT
