# REMI — Real Estate Management Intelligence

An AI-powered property management platform. Upload your reports, get an operational command center with an autonomous AI assistant — grounded in actual portfolio data and a typed real estate ontology.

REMI works for a single property manager running 10 properties or a portfolio leader overseeing multiple managers across hundreds of units. The same platform scales from day-to-day property operations to portfolio-level oversight.

Under the hood it is a layered agent OS: domain ontology, knowledge graph, event system, and LLM runtime — all wired together so the agent can query, analyze, and recommend over real data.

## Quick Start

```bash
# Install with dev dependencies
uv sync --extra dev

# Seed with real AppFolio exports
uv run remi demo --dir data/reports/my-client/

# Or separately
uv run remi seed --dir data/reports/my-client/
uv run remi serve

# Start the frontend (separate terminal)
cd frontend && npm install && npm run dev

# Open http://localhost:3000
```

### Database Lifecycle

```bash
uv run remi db status                 # Backend, entity counts, seed state
uv run remi db reset                  # Drop all tables, recreate
uv run remi db reset --seed <dir>     # Reset + re-seed from reports
```

### CLI Examples

```bash
uv run remi onto search Property      # Search entities by type
uv run remi onto signals              # List signals in the store
uv run remi dashboard                 # Textual TUI dashboard
uv run remi ai ask "How is Marcus doing?"  # Ask the director agent
uv run remi research "Seasonal vacancy patterns across the portfolio"
uv run remi trace list                # Recent reasoning traces
```

## Architecture

REMI is an agent operating system built on four packages. Each has a single job. The directory tree *is* the architecture — an LLM navigating the codebase can infer what exists from `ls` alone.

```
src/remi/
  agent/           AI infrastructure — LLM runtime, signals, graph, vectors, sandbox, documents, tracing
  application/     Real estate product — core models, services, infra stores, API, CLI, tools, agents
  types/           Shared vocabulary — ids, clock, errors, enums, result, text
  shell/           Composition root — DI container, settings, API factory, CLI entry point
```

Dependency direction: `types/ ← agent/ ← application/ ← shell/`. `shell/` imports from everything. `types/` imports nothing.

The `Container` (in `shell/config/container.py`) is pure wiring — it calls factory functions defined in the modules that own the things being built.

### Three Kinds of Knowledge

| Layer | What | Where |
|-------|------|-------|
| **Domain TBox** | What things mean — signal definitions, thresholds, policies, causal chains | `shell/config/domain.yaml` |
| **Ontology** | What entity types exist and how they relate — typed properties, structural links, constraints | `application/infra/ontology/schema.py` |
| **Knowledge Graph** | What actually happened — entities, relationships, observations | `PropertyStore` + `KnowledgeStore` via `BridgedKnowledgeGraph` |

The agent uses the TBox as its rubric for understanding the domain. It queries the knowledge graph through tools and reasons about what it finds — no precomputed signal engine in the loop.

## Agents

Two conversational agents, declared via YAML in `application/agents/`.

| Agent | Purpose | Mode |
|-------|---------|------|
| **Director** (`director/app.yaml`) | Fast Q&A analyst — answers questions using structured data queries and domain awareness. 1-5 tool calls per turn. | Chat |
| **Researcher** (`researcher/app.yaml`) | Deep analytical engine — loads portfolio into DataFrames, runs statistical analysis (regression, clustering, anomaly detection), produces structured research reports. Up to 30 iterations. | Chat |

Internal agents (not user-facing):

| Agent | Purpose |
|-------|---------|
| **Action Planner** (`action_planner/app.yaml`) | Sub-agent that produces structured JSON action plans |

## Tools

Tools registered in `application/tools/`, available to agents:

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
| Dashboard | `/dashboard` | `GET /overview`, `/delinquency`, `/leases/expiring`, `/vacancies`, `/rent-roll/{id}`, `/needs-manager`, `POST /auto-assign` |
| Signals | `/signals` | `GET /`, `/digest`, `/{id}`, `/{id}/explain`, `/{id}/feedback`, `/feedback/summary/{type}` |
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
| Agents | `/agents` | `GET /models`, `GET /`, `POST /{name}/ask` (streaming), `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` |
| Seed | `/seed` | `POST /reports` (from dir) |

### Agent Chat (Streaming)

`POST /api/v1/agents/{name}/ask` streams newline-delimited JSON events (`delta`, `tool_call`, `tool_result`, `done`). The frontend and CLI both use this endpoint — there is no WebSocket chat.

### WebSocket

| Endpoint | Purpose |
|----------|---------|
| `ws://localhost:8000/ws/events` | Real-time server-sent events (ingestion progress, lifecycle) |

### Health

`GET /health` — status, version, uptime, trace/span counts.

## Frontend

Next.js 16 app with React 19, Tailwind 4, and Framer Motion. Connects to the API server.

**Pages** (under `frontend/src/app/(shell)/`):

| Route | Page |
|-------|------|
| `/` | Command center — search, attention signals, portfolio pulse, managers |
| `/ask` | Chat interface — talk to the AI assistant or researcher agent |
| `/delinquency` | Delinquency analysis |
| `/vacancies` | Vacancy tracking |
| `/leases` | Lease expiration analysis |
| `/documents` | Document upload and management |
| `/properties/[id]` | Property detail view |
| `/managers/[id]` | Manager detail view |

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

## Module Map

```
src/remi/

── agent/           AI infrastructure — the agent operating system kernel
  llm/              LLM provider ports + adapters (Anthropic, OpenAI, Gemini)
  vectors/          Embedding ports + adapters
  sandbox/          Code execution ports + adapters (local, Docker)
  observe/          Structured logging (structlog), tracing
  signals/          Signal types, TBox, stores, producers (agent-layer infra)
  graph/            Knowledge graph — types, bridge, retriever
  documents/        Document types, stores, parsers
  db/               Database engine + table metadata
  runtime/          LLM execution loop, tool dispatch, streaming
    conversation/   Thread management, compression
  context/          Perception, context builder, intent classification
  pipeline/         Generic YAML-driven LLM pipeline executor
  sessions/         Chat session persistence
  tools/            Domain-agnostic tools (sandbox, vectors, memory, trace)
  workspace/        Agent working memory (Markdown scratchpad)

── application/      Real estate product (hexagonal)
  core/             Pure business: models, protocols, rules, events
  services/         Orchestration: queries, ingestion, embedding, seeding, search
    ingestion/      Rule-based + LLM ingestion (rules.py, pipeline.py,
                    service.py, persist.py, managers.py)
  infra/            Port implementations: stores (mem, pg), ontology,
                    ports (agent ↔ application bridges)
  tools/            Agent tool registrations
  agents/           RE agent YAML manifests (director, researcher, action_planner)
  realtime/         WebSocket event broadcasting (connection_manager)
  api/              HTTP delivery — vertical slices:
    portfolio/      managers, properties, units, portfolios
    operations/     leases, maintenance, tenants, actions, notes
    intelligence/   signals, dashboard, search, ontology, knowledge, events
    system/         agents, documents, seed, usage, realtime
  cli/              CLI delivery — vertical slices:
    portfolio/      managers, property, units, portfolios, rent_roll
    operations/     leases, maintenance, tenants
    intelligence/   dashboard, search, ontology, graph, trace, research
    system/         agents, documents, seed, demo, vectors, bench, db

── types/           Shared vocabulary — ids, clock, errors, enums

── shell/           Composition root
  config/           DI container, settings, domain.yaml
  api/              FastAPI app factory, middleware, error handler, DI
  cli/              Typer CLI entry point
```

## Data Ingestion

REMI ingests property management report exports (XLSX/CSV) through a two-tier pipeline: **rule-based extraction first, LLM fallback second**.

### Pipeline

1. Upload via `POST /api/v1/documents/upload` or `remi seed --dir <path>`
2. **Rule-based path** (`rules.py`): detects report type from column headers, maps columns to entity fields deterministically, filters junk rows and section headers. Zero API calls, ~1ms per report.
3. **LLM fallback** (only if rules can't match): three-step pipeline (classify → extract → enrich) with ontology schemas injected as context.
4. Schema-driven resolver maps rows to typed domain models — same `resolve_and_persist` path for both tiers.
5. Domain models persisted to PropertyStore + mirrored to KnowledgeStore.
6. Embedding pipeline runs — enables semantic search.

### Rule-Based Extraction (`rules.py`)

The rules engine handles all four AppFolio report types without LLM:

| Report | Detection Signature | Entity Type | Key Behaviors |
|--------|-------------------|-------------|---------------|
| Property Directory | `{property, units, site manager name}` | Property | Creates managers via frequency analysis; filters junk entries; strips "DO NOT USE" prefixes |
| Delinquency | `{property, name, amount receivable}` | Tenant | Maps balances, status, notes; Tags column treated as lease tags (not managers) |
| Lease Expiration | `{property, lease expires, tenant name}` | Lease | Tags column carries manager names; creates units + tenants + leases |
| Rent Roll | `{property, unit, lease from, lease to}` | Unit | Splits BD/BA; tracks section headers as occupancy status context |

### Seeding order

The property directory is always ingested first (detected by column-header heuristic in `PortfolioLoader`). This establishes the source of truth for managers and properties. Subsequent reports add units, leases, tenants, and delinquency data to existing properties.

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
- `domain.yaml` is the source of truth for signal definitions, thresholds, and rules — do not hardcode these in Python
- `types/` is for cross-cutting primitives only — no business logic
- Factory functions live in the module that defines the thing being built, not in the container
- New code depends on the narrowest repository protocol (`LeaseRepository`, not `PropertyStore`)

## License

MIT
