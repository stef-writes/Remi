# REMI Architecture

## Overview

REMI is an **agent operating system for real estate** — a layered runtime that lets AI agents reason over a property management book of business. The architecture enforces a strict four-ring dependency model so the AI kernel remains reusable independent of the real estate domain, and the domain layer remains independent of delivery concerns.

---

## Four-Ring Dependency Model

```
┌─────────────────────────────────────────────────────────────────┐
│  shell/                                                         │
│  Composition root — DI container, settings, FastAPI, Typer CLI │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  application/                                             │  │
│  │  Real estate product — models, views, services, API, CLI  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  agent/                                             │  │  │
│  │  │  AI OS kernel — LLM, sandbox, vectors, runtime      │  │  │
│  │  │                                                     │  │  │
│  │  │  ┌───────────────────────────────────────────────┐  │  │  │
│  │  │  │  types/                                       │  │  │  │
│  │  │  │  Shared primitives — IDs, config, errors      │  │  │  │
│  │  │  └───────────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Dependency arrows always point inward.** `application/` may import from `agent/` and `types/`. `agent/` may only import from `types/`. `types/` imports nothing. `shell/` imports everything and is the only place where the rings are wired together.

---

## Packages

### `types/` — Shared vocabulary

Pure Pydantic models and constants. No I/O, no business logic, no framework imports.

- `config.py` — `RemiSettings` and all nested config shapes
- `paths.py` — canonical filesystem paths (`AGENTS_DIR`, `DOMAIN_YAML_PATH`)

### `agent/` — AI OS kernel

Everything needed to run an AI agent: provider adapters, execution sandbox, memory (with episode extraction and ranked recall), vector search, structured observation, skills, and multi-stage context compression. Contains no real estate concepts — it is domain-agnostic.

```
agent/
  llm/          Provider factory + adapters (Anthropic, OpenAI, Gemini)
  vectors/      Embedding port + adapters (in-memory, Postgres/pgvector)
  sandbox/      Code execution port + backends (local subprocess, Docker)
  graph/        Knowledge graph — types, bridge, retriever
  memory/       Agent memory — store, extraction, recall, importance-ranked
  events/       Typed event bus — the OS-level pub-sub nervous system
  documents/    Document types, in-memory + Postgres content stores
  db/           Async SQLAlchemy engine + agent-owned tables
  runtime/      Agent loop, tool dispatcher, streaming, multi-stage compaction
  tasks/        Supervised multi-agent delegation — TaskSpec, Task, Supervisor, Pool
  skills/       Skill discovery — filesystem-based markdown playbooks
  pipeline/     YAML-driven multi-stage LLM pipeline executor
  workflow/     YAML-driven multi-step workflow engine
  tools/        Kernel primitives only (bash, python, delegate, memory_store, memory_recall)
  sessions/     Chat session persistence (memory / Postgres)
  observe/      Tracing, structured logging, LLM usage ledger
  workspace/    Agent working memory (Markdown scratchpad)
```

Key types: `Sandbox`, `LLMProviderFactory`, `VectorStore`, `Embedder`, `AgentRuntime`, `AgentSessions`, `WorkflowRunner`, `AgentStepNode`, `TaskSupervisor`, `TaskSpec`, `TaskResult`, `MemoryStore`, `MemoryEntry`, `Importance`, `MemoryRecallService`, `extract_episode`, `SkillMetadata`, `SkillContent`, `FilesystemSkillDiscovery`.

### `application/` — Real estate product

The RE domain expressed in hexagonal (ports and adapters) style. Depends on `agent/` for AI infrastructure but defines its own domain models, protocols, and read models. Organized as vertical feature slices — each slice owns its API routes, CLI commands, resolvers, and models.

```
application/
  core/         Domain models (Property, Lease, Tenant, …), protocols,
                business rules, domain events
  views/        Read models — computed views over the domain graph
                (DashboardResolver, RentRollResolver, LeaseResolver, …)
  portfolio/    Portfolio slice — managers, properties, units (API + CLI)
  operations/   Operations slice — leases, maintenance, actions (API + CLI)
  intelligence/ Intelligence slice — dashboard, search, trends (API + CLI)
  ingestion/    Document ingestion pipeline, rules, CLI
  events/       Event feed projections: HTTP poll (api.py) + WebSocket push (ws.py)
  stores/       Port implementations — persistence adapters
    mem.py      InMemoryPropertyStore (dev/test)
    pg/         PostgresPropertyStore + tables + converters
    world.py    REWorldModel (knowledge graph over PropertyStore)
    indexer.py  AgentVectorSearch, AgentTextIndexer adapters
    events.py   InMemoryEventStore
    factory.py  build_store_suite (Postgres vs in-memory)
  tools/        Ingestion tool setup; assertion service functions
  agents/       Agent YAML manifests (director, researcher, …)
  profile.py    Domain profile builder
```

### `shell/` — Composition root

Wires all rings together. Contains no business logic. Registers only kernel tool providers (sandbox, memory, delegation).

```
shell/
  config/
    settings.py   Loads YAML + .env + env-var interpolation → RemiSettings
    container.py  DI wiring — 3 kernel tool providers only
    domain.yaml   Domain TBox — signal definitions, thresholds, rules
  api/
    main.py       FastAPI app factory + lifespan (bootstraps Container)
    middleware.py Request ID + structlog context injection
    error_handler.py Maps domain exceptions to HTTP error envelopes
  cli/
    main.py       Typer entry point (registers all command groups)
    output.py     Structured JSON envelope helpers (success/error)
    client.py     HTTP client mode — proxies to API when REMI_API_URL is set
```

---

## Agent interface — CLI-first

Agents interact with the REMI platform through three layers:

| Layer | What | Where |
|-------|------|-------|
| **Tool** | Kernel primitive exposed via LLM function calling | `agent/tools/` — `bash`, `python`, `delegate_to_agent`, `memory_store`, `memory_recall` |
| **Command** | `remi` CLI subcommand that queries or mutates domain data (JSON output) | `application/{slice}/cli.py` — e.g. `remi portfolio managers`, `remi operations delinquency` |
| **Skill** | Markdown playbook that teaches an agent what to look for and which commands to run | `.remi/skills/{name}/SKILL.md` — loaded at session start |

### How it works

```
HTTP POST /api/v1/agents/{name}/ask
          │
          ▼
  AgentRuntime.ask() (agent/runtime/)
          │
          ├── 5 kernel tools (function calling)
          │   bash, python, delegate_to_agent, memory_store, memory_recall
          │
          ├── bash → remi portfolio managers (JSON output)
          │   bash → remi operations delinquency --manager-id jake
          │   bash → remi intelligence search "delinquent tenants"
          │
          └── python → computation on CLI-retrieved data
              (DataFrames, statistics, trend analysis)
```

When `REMI_API_URL` is set (inside the sandbox), CLI commands proxy to the running API server for fast execution — no container cold start. See `shell/cli/client.py`.

### Streaming response

NDJSON events over the HTTP response body: `delta`, `tool_call`, `tool_running`, `tool_result`, `phase`, `done`, `error`.

### Agents as workflow steps

Agent loops are first-class step types in the workflow engine (`kind: agent`).
A workflow can compose agents with LLM steps, transforms, gates, and fan-out:

```yaml
kind: Workflow
steps:
  - id: classify
    kind: agent
    agent_name: director
    mode: ask

  - id: needs_research
    kind: gate
    condition: "'research' in steps.classify"
    depends_on: [classify]

  - id: research
    kind: agent
    agent_name: researcher
    depends_on: [needs_research]
```

---

## Data flow: document ingestion

```
User uploads CSV/XLSX
        │
        ▼
POST /api/v1/documents/upload
        │
        ▼
DocumentIngestService.ingest_document()
        │
        ├─ Rule engine (ingestion/rules.py)
        │   Deterministic column detection + mapping for known report types
        │   (Property Directory, Rent Roll, Delinquency, Lease Expiration)
        │
        └─ LLM fallback (ingestion/pipeline.py)
            Three-stage YAML pipeline: classify → extract → enrich
            Only used for unknown report formats
        │
        ▼
resolve_and_persist()
        │
        ├── PropertyStore.upsert_*()   (writes domain entities)
        └── ContentStore.put()         (stores raw document bytes + metadata)
        │
        ▼
EventBus.publish("ingestion.complete") → feed/ws + GET /feed
```

---

## Data flow: agent conversation

```
POST /api/v1/agents/director/ask  { "message": "...", "session_id": "..." }
        │
        ▼
AgentRuntime.ask()
        │
        ├── SkillDiscovery → load skill catalog into system prompt
        ├── MemoryRecallService → inject relevant memories
        ├── ContextBuilder.build()
        │   Pulls: domain TBox signals, world model summary
        │
        ├── LLMProvider.complete()   (streaming)
        │
        └── ToolDispatcher.dispatch(tool_call)
              │
              ├── bash             → remi CLI commands (JSON output)
              │                      e.g. remi portfolio managers
              │                      e.g. remi operations delinquency
              ├── python           → computation on retrieved data
              ├── memory_store     → MemoryStore.write()
              ├── memory_recall    → MemoryStore.search()
              └── delegate_to_agent → TaskSupervisor.spawn_and_wait()
                    │
                    ├── TaskSpec (objective, constraints, parent_run_id)
                    ├── TaskPool (bounded concurrency, backpressure)
                    ├── AgentRuntime.ask() (specialist agent)
                    └── TaskResult (structured output, usage, trace)
                    │
                    EventBus: task.spawned / task.completed / task.failed
        │
        ▼
NDJSON stream: delta / tool_call / tool_result / done
```

---

## Storage backends

| Layer | In-memory (dev) | Postgres (prod) |
|-------|-----------------|-----------------|
| Domain (properties, leases, …) | `InMemoryPropertyStore` | `PostgresPropertyStore` |
| Document content | `InMemoryContentStore` | `PostgresContentStore` |
| Vector embeddings | `InMemoryVectorStore` | `PostgresVectorStore` (JSON today; pgvector planned) |
| Agent memory (4 namespaces) | `InMemoryMemoryStore` | `PostgresMemoryStore` |
| Chat sessions | `InMemoryChatSessionStore` | `PostgresChatSessionStore` (stubbed) |
| Traces/spans | `InMemoryTraceStore` | `PostgresTraceStore` (stubbed) |
| Domain events | `InMemoryEventStore` | not yet implemented |

Backend selection is controlled by `state_store.backend` (domain + content) and per-layer `vectors.backend`, `memory.backend`, `tracing.backend`, `sessions.backend` in the active YAML config.

---

## Sandbox backends

| Backend | Mechanism | Isolation | Use case |
|---------|-----------|-----------|----------|
| `local` | `asyncio.create_subprocess_exec` + persistent Python interpreter per session | Process-level only; shares host kernel and network | Single-server dev/prod with trusted operators |
| `docker` | Docker-outside-of-Docker; one container per session using `remi-sandbox` image | Container boundary; no access to host filesystem or API secrets | Stronger isolation; requires Docker socket mount |

The active backend is selected by `settings.sandbox.backend` (env var `REMI_SANDBOX__BACKEND`).

Sessions idle longer than `settings.sandbox.session_ttl_seconds` are automatically reaped by a background task in the server lifespan (every 5 minutes).

---

## Networking

In a single-process deployment all internal calls are loopback (`127.0.0.1`). In containerised deployments the sandbox containers reach the API via Docker's internal network:

```
[remi-api container]
    │
    ├── spawns → [remi-sandbox container]
    │                │
    │                └── remi CLI → REMI_API_URL (e.g. http://api:8000)
    │                    (client mode: shell/cli/client.py proxies to API)
    │                           │
    │            [Docker bridge network: remi_internal]
    │                           │
    └───────────────────────────┘
```

Set `REMI_API__INTERNAL_API_URL=http://api:8000` so CLI commands inside the sandbox resolve to the correct API address.

---

## Settings resolution order

For each setting, later sources win:

1. Default in `RemiSettings` / nested model
2. `config/base.yaml`
3. `config/{REMI_CONFIG_ENV}.yaml`
4. `.env` file (does not override already-set env vars)
5. Environment variables (`DATABASE_URL`, `ANTHROPIC_API_KEY`, `REMI_LLM_*`, `REMI_SANDBOX__*`, `REMI_API__*`, etc.)

---

## Key invariants

- `types/` imports nothing from `agent/`, `application/`, or `shell/`
- `agent/` never imports from `application/` or `shell/`
- `application/` never imports from `shell/`
- `container.py` is pure wiring — no business logic, no factory decisions
- Factory functions live in the module that owns the thing being built
- Domain signal definitions, thresholds, and rules live in `shell/config/domain.yaml` — never hardcoded in Python
- The agent reasons over data via tools; there is no precomputed signal engine
