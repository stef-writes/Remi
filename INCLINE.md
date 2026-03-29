# Incline Intelligence — Framework Architecture

> **Incline** is the domain-agnostic AI infrastructure.
> **REMI** (Real Estate Management Intelligence) is the first product built on it.

This document defines the boundary. If you're adding code, the question is:
*"Would this exist if we replaced real estate with healthcare, logistics, or finance?"*
If yes, it belongs to Incline. If no, it belongs to REMI.

---

## What Incline Provides

Incline is a framework for building **domain-intelligent AI products** — systems
where institutional expertise (not just data) shapes what the AI perceives,
reasons about, and recommends.

### Core Capabilities

| Capability | What it does | Key modules |
|-----------|-------------|-------------|
| **Ontology System** | Schema-driven knowledge representation: object types, links, codification, traversal | `domain.ontology`, `infrastructure.ontology` |
| **Entailment Engine** | TBox rules evaluated against ABox facts → typed Signals with evidence | `domain.signals`, `infrastructure.entailment` |
| **Signal Framework** | Producer pipeline (rule-based, statistical, learned), composite merging, feedback loop | `domain.signals.producers`, `infrastructure.entailment.composite` |
| **Hypothesis Pipeline** | Inductive discovery: pattern detection → hypothesis → confirmation → TBox graduation | `domain.signals.hypothesis`, `infrastructure.entailment.pattern_detector` |
| **Graph Runtime** | YAML-defined app graphs with typed modules, state management, event bus | `runtime.engine`, `domain.graph`, `domain.modules` |
| **LLM Providers** | Multi-provider abstraction (OpenAI, Anthropic, Gemini) with config-driven selection | `infrastructure.llm` |
| **Agent System** | Config-driven agent loop (AgentNode), tool dispatch, mode switching | `domain.modules.builtins.llm` |
| **Sandbox** | Isolated subprocess execution for agent-written code, with session management | `domain.sandbox`, `infrastructure.sandbox` |
| **Trace / Observability** | Hierarchical spans with epistemological categories (entailment, perception, LLM, tool, reasoning) | `domain.trace`, `infrastructure.trace` |
| **Knowledge Graph** | Entity/relationship store with namespace isolation | `domain.memory`, `infrastructure.memory` |
| **Vector Retrieval** | Embedding pipeline, semantic search, pluggable embedders | `domain.retrieval`, `infrastructure.vectors` |
| **Tools Framework** | Registry-based tool system, definition/dispatch, agent-callable | `domain.tools`, `infrastructure.tools` |
| **Chat Service** | Session management, agent runner, WebSocket transport | `domain.chat`, `application.chat`, `interfaces.api.realtime` |
| **Document System** | Upload, parse (CSV/XLSX), store, query — domain-agnostic tabular data | `domain.documents`, `infrastructure.documents` (except `appfolio_schema`) |
| **Platform API** | REST endpoints for apps, runs, ontology, signals, hypotheses, health | `interfaces.api.platform`, `.ontology`, `.signals`, `.hypotheses` |
| **Framework CLI** | `app`, `node`, `tool`, `provider`, `onto`, `trace`, `serve` commands | `interfaces.cli.framework`, `.ontology`, `.trace` |

### The Key Abstraction

A product built on Incline provides:

1. **A domain.yaml** — TBox definitions (signals, thresholds, policies, causal chains)
2. **A domain store** — the ABox adapter (PropertyStore for RE, PatientStore for health, etc.)
3. **Agent workflows** — YAML app definitions with domain-specific prompts
4. **Core type bindings** — mapping domain entities to OntologyStore
5. **Evaluators** — signal evaluation logic for domain-specific conditions
6. **Domain API/CLI** — routes and commands for domain-specific queries

Everything else — the runtime, the entailment engine, the ontology system, the
LLM loop, the trace layer, the sandbox — is Incline.

---

## Package Boundary

The codebase uses `remi.*` as the Python package namespace. The Incline/REMI
boundary is structural, not (yet) a separate installable package. The rule:

### Incline (framework) — domain-agnostic

```
domain/
  common/          — shared types
  graph/           — app/module definitions, validation
  modules/         — module ports + all builtins (AgentNode, router, etc.)
  tools/           — tool port
  state/           — state store port + models
  trace/           — trace port + span types
  sandbox/         — sandbox port + types
  retrieval/       — vector/embedder ports
  memory/          — knowledge graph port (entities, relationships)
  ontology/        — OntologyStore ABC, ObjectTypeDef, LinkTypeDef
  signals/         — SignalProducer, SignalStore, DomainOntology, TBox types
  chat/            — ChatSession, ChatEvent, ports
  documents/       — Document model, DocumentStore
  viewmodels/      — UI contract types

infrastructure/
  config/          — settings (InclineContainer lives here)
  loaders/         — YAML loading
  registries/      — app + module registries
  stores/          — state store adapters
  llm/             — provider implementations
  trace/           — tracer, in-memory trace store
  sandbox/         — LocalSandbox, SandboxSeeder, client template
  vectors/         — embedder, pipeline, in-memory store
  entailment/      — EntailmentEngine, CompositeProducer, StatisticalProducer,
                     PatternDetector, HypothesisGraduator, signal/feedback/hypothesis stores
  ontology/        — BridgedOntologyStore, bootstrap, RemoteOntologyStore
  memory/          — in-memory knowledge store
  chat/            — in-memory chat session store
  tools/           — tool implementations (ontology, documents, memory, sandbox, trace, vectors)
  documents/       — parsers, in-memory document store

application/
  app_management/  — register/validate apps
  execution/       — run apps
  state_access/    — state queries
  chat/            — ChatAgentService (agent runner)

runtime/           — graph runner, event bus, retry policy, runtime context

shared/            — clock, IDs, errors, result, enums, paths

interfaces/
  api/platform/    — health, apps, runs
  api/ontology/    — ontology REST
  api/signals/     — signal REST
  api/hypotheses/  — hypothesis lifecycle REST
  api/realtime/    — WebSocket transport
  api/agents/      — /ask endpoint
  cli/framework/   — app, node, tool, provider commands
  cli/ontology     — onto commands
  cli/trace        — trace commands
  cli/vectors      — vector commands
  cli/agents/      — ask, chat commands
```

### REMI (product) — real estate specific

```
domain/
  properties/      — PropertyManager, Property, Unit, Lease, Tenant, etc.
                     PropertyStore port, enums, metrics, RE EntityType

infrastructure/
  properties/      — InMemoryPropertyStore
  knowledge/       — RE ingestion pipeline, enrichment
  documents/
    appfolio_schema.py  — AppFolio report detection

application/
  property_management/  — PM query services
  dashboard/            — RE dashboard aggregation
  snapshots/            — PM performance snapshots
  document_management/  — RE ingest orchestration

interfaces/
  api/managers/         — PM API
  api/properties/       — property API
  api/portfolios/       — portfolio API
  api/leases/           — lease API
  api/maintenance/      — maintenance API
  api/dashboard/        — dashboard API
  api/documents/        — document upload (RE-flavored)
  cli/properties/       — RE CLI commands

workflows/
  domain.yaml                  — RE TBox
  director/app.yaml            — RE director agent
  knowledge_enricher/app.yaml  — RE enrichment agent

frontend/                      — Next.js RE product UI
```

### The Gray Zone (framework code with RE coupling to fix)

| File | Issue | Fix |
|------|-------|-----|
| `domain/signals/types.py` `EntityType` | Enum values are RE entity names | Moved to `domain/properties/entity_types.py`; framework uses `str` |
| `infrastructure/ontology/bridge.py` | `_core_types` hardcodes 7 RE types | Now accepts `core_types` as constructor arg |
| `infrastructure/config/container.py` | Single class wires both layers | Split into `InclineContainer` + `Container(InclineContainer)` |

---

## How to Add a New Domain

To build "Acme Health Intelligence" on Incline:

1. Create `domain/patients/` with Patient, Encounter, Claim models + PatientStore port
2. Create `infrastructure/patients/` with InMemoryPatientStore
3. Write `workflows/domain.yaml` with health signals (ReadmissionRisk, CodingAnomaly, etc.)
4. Write `workflows/clinician/app.yaml` with health-domain agent prompt
5. Map core types: `{"Patient": (store.get_patient, store.list_patients), ...}`
6. Subclass `InclineContainer` → `HealthContainer` to wire health stores + services
7. Add health-specific API routes and CLI commands

The entailment engine, ontology system, graph runtime, LLM loop, trace layer,
sandbox, and every tool works identically. Only the TBox content and the
domain store change.
