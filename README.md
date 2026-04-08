# REMI — Real Estate Management Intelligence

An AI agent operating system for property management. REMI gives a director-level view across an entire book of business: portfolio health, delinquency, lease expirations, maintenance trends, and tenant dynamics — all queryable through natural language agents backed by real property data.

---

## What it does

- **Document ingestion** — upload AppFolio CSV/Excel report exports; REMI classifies and parses them with a rule-based pipeline (LLM fallback for unknown formats)
- **Knowledge graph** — property managers, properties, units, leases, tenants, and maintenance requests stored as a connected graph
- **CLI-first agent interface** — agents interact with the platform through `remi` CLI commands (JSON output), not function-calling tools. Five kernel primitives (`bash`, `python`, `delegate_to_agent`, `memory_store`, `memory_recall`) plus a rich CLI command surface
- **Conversational agents** — director agent (fast Q&A), researcher agent (deep statistical analysis with Python sandbox), and specialist sub-agents (document ingestion, manager review, action planning)
- **Skills** — markdown playbooks that teach agents domain knowledge and CLI command patterns
- **REST API + WebSocket** — all data queryable over HTTP; lifecycle events broadcast via WebSocket
- **CLI** — full Typer CLI for portfolio queries, operations, intelligence, ingestion, and administration

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full four-ring diagram and data flow.

```
types/ ← agent/ ← application/ ← shell/
```

| Ring | Package | Responsibility |
|------|---------|----------------|
| Core | `types/` | Shared primitives — IDs, config shapes, error types. Imports nothing. |
| AI kernel | `agent/` | LLM providers, sandbox, vectors, graph, runtime loop, tools. Imports `types/` only. |
| RE product | `application/` | Domain models, views, services, API/CLI slices, infra adapters. Imports `agent/` + `types/`. |
| Composition root | `shell/` | DI container, settings loader, FastAPI app, Typer CLI. Imports everything. |

---

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (`pip install uv`)
- An LLM API key (Anthropic Claude recommended; OpenAI and Gemini also supported)
- Postgres 15+ for production; in-memory stores work for development

---

## Quickstart (local dev)

```bash
# 1. Clone and install
git clone https://github.com/your-org/remi
cd remi
uv sync --extra dev

# 2. Copy and fill environment variables
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY (or OPENAI_API_KEY)

# 3. Start the API server (in-memory stores, no DB required)
uv run remi serve

# 4. Open the frontend
cd frontend && npm install && npm run dev
# Visit http://localhost:3000
```

### With Postgres

```bash
# Start Postgres locally
docker compose up postgres -d

# Set DATABASE_URL in .env
echo 'DATABASE_URL=postgresql://remi:remi@localhost:5433/remi' >> .env
echo 'REMI_CONFIG_ENV=dev' >> .env

uv run remi serve
```

---

## Environment variables

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic key (used when `REMI_LLM_PROVIDER=anthropic`) |
| `OPENAI_API_KEY` | OpenAI key (used when provider is `openai`; also default embeddings) |

### Database

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres DSN (`postgresql://user:pass@host:5432/db`). Omit for in-memory. |
| `APPOS_DATABASE_URL` | Alias for `DATABASE_URL` used in production configs. |

### LLM / Embeddings

| Variable | Description | Default |
|----------|-------------|---------|
| `REMI_LLM_PROVIDER` | `anthropic` \| `openai` \| `gemini` | `anthropic` |
| `REMI_LLM_MODEL` | Model name | `claude-sonnet-4-20250514` |
| `REMI_EMBEDDINGS_PROVIDER` | `openai` \| `voyage` | `openai` |
| `REMI_EMBEDDINGS_MODEL` | Embedding model | `text-embedding-3-small` |
| `REMI_EMBEDDINGS_DIMENSIONS` | Output dimensions | `1536` |
| `VOYAGE_API_KEY` | Voyage AI key (when using Voyage embeddings) | |
| `GOOGLE_API_KEY` | Google key (when provider is `gemini`) | |

### Sandbox

| Variable | Description | Default |
|----------|-------------|---------|
| `REMI_SANDBOX__BACKEND` | `local` or `docker` | `local` |
| `REMI_SANDBOX__DEFAULT_TIMEOUT` | Execution timeout (seconds) | `30` |
| `REMI_SANDBOX__SESSION_TTL_SECONDS` | Idle session reap interval (`0` = off) | `3600` |

### API / Networking

| Variable | Description | Default |
|----------|-------------|---------|
| `REMI_CONFIG_ENV` | Config YAML to load (`base`, `dev`, `prod`, `local`) | `base` |
| `REMI_API__INTERNAL_API_URL` | Internal URL the sandbox uses to call the API. Set to the service hostname in Docker/K8s deployments. | `http://127.0.0.1:{port}` |

---

## Configuration files

YAML configs live in `config/`. The active config is selected by `REMI_CONFIG_ENV`:

| File | Use |
|------|-----|
| `config/base.yaml` | Defaults (in-memory stores, port 8000) |
| `config/dev.yaml` | Postgres enabled, dev log level |
| `config/local.yaml` | Machine-local overrides (git-ignored) |
| `config/prod.yaml` | Production: Postgres, structured logging, no CORS wildcard |

`${VAR}` in YAML values is interpolated from environment variables.

---

## CLI reference

```bash
uv run remi --help

# Server
uv run remi serve                    # Start API server

# Portfolio
uv run remi portfolio managers       # List managers with metrics (JSON)
uv run remi portfolio properties     # List properties
uv run remi portfolio rent-roll <id> # Rent roll for a property
uv run remi portfolio manager-review <id>  # Full manager review
uv run remi portfolio rankings       # Rank managers by metric

# Operations
uv run remi operations leases        # List leases
uv run remi operations maintenance   # Maintenance requests
uv run remi operations delinquency   # Delinquency board
uv run remi operations expiring-leases     # Leases expiring within N days
uv run remi operations create-action --title "..." --manager-id "..."
uv run remi operations create-note   --content "..." --entity-type "..." --entity-id "..."

# Intelligence
uv run remi intelligence dashboard   # Portfolio overview
uv run remi intelligence search "delinquent"  # Semantic search
uv run remi intelligence vacancies   # Vacancy tracker
uv run remi intelligence trends delinquency   # Time-series trends
uv run remi intelligence assert-fact --entity-type "..." --properties '{...}'
uv run remi intelligence add-context --entity-type "..." --entity-id "..." --context "..."

# Ingestion
uv run remi ingestion upload report.csv      # Ingest a document
uv run remi ingestion documents              # List ingested documents
uv run remi ingestion document-search "query"  # Search document content

# System
uv run remi seed reports/            # Ingest a folder of AppFolio CSVs
uv run remi db reset                 # Drop and recreate tables (dev only)
```

All commands output structured JSON by default (see `shell/cli/output.py` for the envelope format). Pass `--table` for human-readable output where supported.

---

## Deployment

### Single server (Digital Ocean Droplet / any VPS)

The simplest production topology: one Droplet running the API + a managed Postgres database (e.g. Digital Ocean Managed Databases).

```bash
# On the server
export DATABASE_URL="postgresql://..."
export ANTHROPIC_API_KEY="..."
export REMI_CONFIG_ENV=prod

# Build and start (subprocess sandbox — no Docker socket needed)
docker build -t remi-api .
docker run -d -p 8000:8000 \
  -e DATABASE_URL -e ANTHROPIC_API_KEY -e REMI_CONFIG_ENV \
  remi-api
```

The default `sandbox.backend=local` runs agent code as a subprocess inside the API container. This is adequate for a single-tenant deployment.

### Docker Compose (with container sandbox)

For stronger isolation, use the Docker-outside-of-Docker sandbox:

```bash
# 1. Build the sandbox image first
docker compose --profile build build sandbox

# 2. Copy and fill .env
cp .env.example .env

# 3. Start Postgres + API
docker compose --profile prod up -d
```

The compose file sets `REMI_SANDBOX__BACKEND=docker` and
`REMI_API__INTERNAL_API_URL=http://api:8000` so sandbox containers on the
Docker network can reach the API.

### Digital Ocean App Platform

App Platform does not expose the Docker socket, so use `REMI_SANDBOX__BACKEND=local`. Connect to a Managed Database by setting `DATABASE_URL` from the App Platform environment variable dashboard.

```
REMI_CONFIG_ENV=prod
DATABASE_URL=<app-platform-injected>
ANTHROPIC_API_KEY=<secret>
OPENAI_API_KEY=<secret>
```

### Supabase (managed Postgres)

Supabase uses PgBouncer on port 6543 (transaction mode). Use the **direct connection** (port 5432) for asyncpg:

```
DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

> Transaction-mode pooling (port 6543) breaks prepared statements with asyncpg. Always use the direct connection URL.

---

## Sandbox security model

REMI includes two sandbox backends:

**`local` (default)** — Agent code runs as a long-lived Python subprocess on the host. Variables persist between tool calls. Shell commands run one-shot via `asyncio.create_subprocess_shell`. A command blocklist provides basic defense-in-depth but is **not** a strong security boundary. Suitable for trusted single-user or internal deployments.

**`docker`** — Each session spawns an isolated `remi-sandbox` container via the Docker socket. The sandbox image contains only analytics packages and has no access to the API source tree or secrets. Suitable for deployments where agent code must be more strongly isolated.

Neither backend provides OS-level namespacing equivalent to gVisor/Firecracker. For fully untrusted multi-tenant code execution, additional infrastructure hardening is required.

---

## Project structure

```
src/remi/
  types/          Shared vocabulary — IDs, config shapes, error types
  agent/          AI OS kernel (domain-agnostic)
    llm/          LLM provider adapters (Anthropic, OpenAI, Gemini)
    vectors/      Embedding adapters + vector store
    sandbox/      Code execution (local subprocess / Docker)
    graph/        Knowledge graph types, bridge, retriever
    memory/       Agent memory — store, extraction, recall, importance-ranked
    events/       Typed event bus — OS-level pub-sub
    documents/    Document types, stores, parsers
    db/           Async SQLAlchemy engine + agent-owned tables
    runtime/      Agent loop, tool dispatch, streaming, multi-stage compaction
    tasks/        Supervised multi-agent delegation (TaskSpec, Supervisor, Pool)
    skills/       Skill discovery — filesystem-based markdown playbooks
    pipeline/     YAML-driven multi-stage LLM pipeline executor
    workflow/     YAML-driven multi-step workflow engine
    tools/        Kernel tool primitives only (bash, python, delegate, memory)
    sessions/     Chat session persistence
    observe/      Structured logging, tracing, LLM usage ledger
    workspace/    Agent working memory (Markdown scratchpad)
  application/    Real estate product (hexagonal)
    core/         Domain models, protocols, business rules, events
    views/        Read models — computed views over the domain
    portfolio/    Portfolio slice — managers, properties, units (API + CLI)
    operations/   Operations slice — leases, maintenance, actions (API + CLI)
    intelligence/ Intelligence slice — dashboard, search, trends (API + CLI)
    ingestion/    Document ingestion pipeline (API + CLI)
    events/       Event feed projections — HTTP poll + WebSocket push
    stores/       Port implementations — Postgres/in-memory, world model, indexer
    tools/        Ingestion tool setup; assertion service functions
    agents/       Agent YAML manifests (director, researcher, …)
    profile.py    Domain profile builder
  shell/          Composition root
    config/       DI container, settings loader, domain.yaml
    api/          FastAPI app factory, middleware, error handler
    cli/          Typer entry, JSON envelope helpers, HTTP client mode
```

---

## Contributing

```bash
# Install dev dependencies
uv sync --extra dev

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type check
uv run mypy src/

# Tests
uv run pytest
```
