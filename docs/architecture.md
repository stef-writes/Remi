# REMI Architecture

## Philosophy

REMI is an **agent operating system** for property management
intelligence. To the end user it feels like a director's dashboard with
a very capable autonomous assistant. Under the hood it is a layered
runtime: domain ontology, signal engine, knowledge graph, and LLM
execution loop — all wired so the agent can reason over real portfolio
data.

Every structural decision flows from one principle: **the directory tree
is the architecture.**

Four top-level packages:

1. **`agent/`** — Agent OS kernel. LLM runtime, signals, knowledge
   graph, vectors, sandbox, documents, tracing — everything the agent
   needs to think, remember, perceive, and act.
2. **`domain/`** — Real estate product intelligence. Entity models,
   persistence, queries, evaluators, ingestion, ontology, search, tools.
3. **`types/`** — Shared vocabulary. Pure primitives used by both.
4. **`shell/`** — Composition root. DI container, settings, API, CLI.

Dependency direction: `domain/` imports from `agent/` — never the
reverse. `shell/` imports from both. `types/` imports nothing.

---

## The Four Packages

```
src/remi/
  ┌───────────────────────────────────────────────────────────────┐
  │  agent/         AI infrastructure                             │
  │    llm/         LLM provider ports + adapters                 │
  │    vectors/     Embedding ports + adapters                    │
  │    sandbox/     Code execution ports + adapters               │
  │    observe/     Structured logging + tracing                  │
  │    signals/     Signal types, stores, engine, composite       │
  │    graph/       Knowledge graph types, bridge, retriever      │
  │    documents/   Document types, stores, parsers               │
  │    db/          Database engine + table metadata              │
  │    runtime/     Execution loop, tool dispatch, streaming      │
  │    context/     Perception, context builder, intent           │
  │    conversation/ Thread management, compression               │
  │    tools/       Domain-agnostic tool implementations          │
  ├───────────────────────────────────────────────────────────────┤
  │  domain/        Real estate product intelligence              │
  │    portfolio/   Entity DTOs + protocols + business rules      │
  │    stores/      RE persistence adapters                       │
  │    queries/     RE query services (dashboard, rent roll, ...) │
  │    evaluators/  RE signal producers (delinquency, lease, ...) │
  │    ingestion/   RE inbound data pipeline                      │
  │    ontology/    RE knowledge graph schema                     │
  │    search/      RE-aware hybrid search + pattern detection    │
  │    tools/       RE agent capabilities                         │
  │    agents/      RE agent YAML manifests                       │
  ├───────────────────────────────────────────────────────────────┤
  │  types/         Shared vocabulary — ids, clock, errors, enums │
  ├───────────────────────────────────────────────────────────────┤
  │  shell/         Composition root — DI, settings, API, CLI     │
  └───────────────────────────────────────────────────────────────┘
```

---

## `agent/` — AI Infrastructure

The agent owns every subsystem needed for AI operation.

### `agent/llm/`
LLMProvider ABC, Message, ToolDefinition, streaming types.
Adapters: OpenAI, Anthropic, Gemini. Factory: `build_provider_factory()`.

### `agent/vectors/`
Embedder and VectorStore ABCs. In-memory store. `build_embedder()`.

### `agent/sandbox/`
Sandbox ABC for isolated code execution. Local subprocess and Docker
backends. Policy enforcement. `remi_data` bridge for sandbox-to-API calls.

### `agent/observe/`
Tracer, Span, TraceStore. structlog configuration. Event constants.

### `agent/signals/`
Signal framework: SignalDefinition, DomainTBox, SignalProducer,
SignalStore/FeedbackStore ABCs. CompositeProducer.
Generic signal producers: CompositionProducer, StatisticalProducer.
Entailment primitives: MakeSignalFn, EntailmentResult.

### `agent/graph/`
Knowledge graph: Entity, Relationship, KnowledgeGraph ABCs.
BridgedKnowledgeGraph, GraphRetriever (vector + graph fusion).

### `agent/documents/`
Document model, DocumentStore ABC. CSV/XLSX parsing. Postgres adapter.

### `agent/db/`
SQLAlchemy async engine factory. Table metadata.

### `agent/runtime/`
ChatAgentService, agent loop, AgentNode, LLM bridge, tool executor.

### `agent/context/`
ContextBuilder, ContextFrame, intent classification, rendering.

### `agent/conversation/`
Thread management, long-thread compression.

### `agent/ingestion/`
Generic LLM pipeline runner. YAML-driven step execution via
LLMProvider.complete(). No chat runtime overhead.

### `agent/tools/`
Domain-agnostic tools: sandbox execution, HTTP, memory, vectors,
delegation, trace inspection, tool registry.

**Two agent modes:**
- **Conversational agents** run inside REMI. They use `domain/tools/`.
- **Code-first agents** run in `agent/sandbox/`. They use `remi_data`.

---

## `domain/` — Real Estate Product

All property management business logic. Replace this to build a
different product.

### `domain/portfolio/`
Entity DTOs (Property, Unit, Tenant, Lease, Manager, Portfolio).
Narrow repository protocols. Business rule functions.

### `domain/stores/`
PropertyStore implementations: in-memory, Postgres. Rollup stores.

### `domain/queries/`
Dashboard, rent roll, leases, properties, portfolios, maintenance,
managers, snapshots, metrics, auto-assignment.

### `domain/evaluators/`
RE signal producers: delinquency, lease cliff, maintenance backlog,
portfolio risk, threshold, trend. EntailmentEngine dispatches rules.
Generic producers (composition, statistical) live in `agent/signals/`.

### `domain/ingestion/`
Ontology-driven inbound flow: upload → parse → LLM extraction → resolve
to domain models → persist to PropertyStore + KnowledgeStore. The resolver
maps LLM rows directly to typed Pydantic models with no intermediate event
layer. Manager classification, seed service, embedding pipeline.
Generic LLM pipeline runner lives in `agent/ingestion/`.

### `domain/ontology/`
RE knowledge graph schema. `seed_knowledge_graph()`.

### `domain/search/`
RE-aware hybrid search service.

### `domain/tools/`
Conversational agent capabilities: `register_all_tools()`.
Ontology, documents, search, actions, workflows, snapshots.

### `domain/agents/`
YAML manifests: director, researcher, action planner, document ingestion.

---

## `types/` — Shared Vocabulary

No I/O. No deps beyond pydantic/stdlib.
IDs, clock, errors, enums, Result[T], text utilities.

---

## `shell/` — Composition Root

The only place that knows about all packages.

- `config/container.py` — DI Container, calls `build_*()` factories
- `config/settings.py` — Pydantic settings from env vars
- `config/domain.yaml` — Signal thresholds, rules, domain config
- `api/` — FastAPI routes
- `cli/` — Typer CLI commands

---

## Dependency Flow

```
shell/ ──> everything (composition root)

domain/tools/       ──> domain/queries/, domain/evaluators/, domain/ingestion/,
                        domain/ontology/, domain/search/, agent/
domain/agents/      ──> agent/
domain/evaluators/  ──> domain/portfolio/, domain/stores/, agent/signals/
domain/ingestion/   ──> domain/portfolio/, domain/stores/, agent/documents/,
                        agent/signals/, agent/ingestion/
domain/queries/     ──> domain/portfolio/, domain/stores/, agent/graph/
domain/ontology/    ──> agent/graph/
domain/search/      ──> agent/graph/, agent/vectors/
domain/stores/      ──> domain/portfolio/, agent/db/
domain/portfolio/   ──> types/

agent/ subsystems depend on each other and on types/
types/ ──> nothing
```

`domain/` imports from `agent/` — never the reverse.

---

## Key Decisions

1. **Agent operating system.** REMI is a runtime, not a library. The
   agent is the primary user of every subsystem.

2. **Four packages.** `agent/`, `domain/`, `types/`, `shell/`. The
   architecture is the `ls`.

3. **Agent OS kernel.** All AI infrastructure under `agent/`. LLM,
   vectors, sandbox, signals, graph, documents, DB, tracing — the
   agent's subsystems, not independent libraries.

4. **Domain consolidation.** All RE product intelligence under `domain/`.
   Nine subpackages that form one coherent product surface.

5. **Clean dependency direction.** `domain/` -> `agent/` -> `types/`.
   Never the reverse. `shell/` wires both sides.

6. **Ontology-driven ingestion.** The domain ontology defines entity
   types; the LLM extraction pipeline uses the schema in its prompts;
   the resolver maps rows directly to typed domain models. No intermediate
   event layer.

7. **Factory pattern.** Each module owns its `build_*()`. Container
   calls factories — never inlines assembly.

8. **Two agent modes.** Conversational agents use `domain/tools/`.
   Code-first agents use `agent/sandbox/` with `remi_data` bridge.
