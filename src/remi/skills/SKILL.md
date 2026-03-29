---
name: remi
description: >-
  Real Estate Management Intelligence — AI-powered property analytics and
  operations across portfolios, properties, units, leases, tenants, and
  maintenance. Built on a signal-layer architecture: the signal pipeline
  (rule-based + statistical) detects domain signals from facts; the LLM
  explains, connects, and recommends.
---

# REMI — Real Estate Management Intelligence

A layered AI platform for directors of property management. Designed for human
operators and AI agents operating on the same grounded interface.

See `ARCHITECTURE.md` at the repo root for the full system design.

## Installation

```bash
uv pip install -e ".[dev]"
```

**Prerequisites:**
- Python 3.11+
- An LLM provider API key (OpenAI, Anthropic, or Gemini) for AI agent features

## Core Concepts

### TBox vs ABox

**TBox (Terminological Box):** What things mean. Domain expertise formalized.
Lives in `src/remi/workflows/domain.yaml`. Defines signal concepts, thresholds,
inference rules, policies, and causal chains. Editable by domain experts.

**ABox (Assertion Box):** What actually happened. Individual facts about
properties, units, leases, tenants, maintenance. Lives in `PropertyStore`,
`KnowledgeStore`, and `DocumentStore`.

**Signals:** What is currently true, derived by the signal pipeline from
known TBox rules and statistical analysis. Pre-computed. Named. Evidenced.
Severity-ranked. This is the layer the director and the agents navigate.

The system has two pipelines:

**Deduction pipeline** (`CompositeProducer`) — applies known physics:
- **RuleBasedProducer** (EntailmentEngine) — evaluates TBox rules against
  ABox facts. Deterministic, auditable. Includes both static rules from
  `domain.yaml` and graduated learned rules from confirmed hypotheses.
- **StatisticalProducer** — z-score outlier detection and categorical
  concentration analysis across all ontology types. Data-driven, no
  hand-authored rules needed.

**Induction pipeline** (`PatternDetector`) — discovers new physics:
- Scans ABox data through OntologyStore. Proposes candidate TBox entries
  as `Hypothesis` objects (threshold signals, causal chains, anomaly patterns).
- Hypotheses are reviewed (confirm/reject), then graduated into the live TBox
  via `HypothesisGraduator`. Once graduated, they become deductive rules.

The `FeedbackStore` tracks signal outcomes (acknowledged, dismissed, acted_on)
to enable threshold tuning and severity re-weighting over time.

### The Twelve Domain Signals

The signal pipeline detects these. The LLM explains and acts on them.

**Portfolio Health**
- `OccupancyDrift` — occupancy declining across 2+ consecutive periods
- `DelinquencyConcentration` — delinquency rate exceeds threshold of gross rent roll
- `LeaseExpirationCliff` — >30% of leases expiring within 60 days, no renewals underway
- `VacancyDuration` — units vacant beyond market-normal window (default 30 days)
- `MaintenanceBacklog` — open work orders aging without resolution

**Manager Performance**
- `OutlierPerformance` — manager significantly below peer group
- `PerformanceTrend` — direction of change (improving or deteriorating)
- `CommunicationGap` — situations in data the director hasn't been told about

**Operational**
- `PolicyBreach` — required action didn't happen (notice not filed, renewal not sent)
- `LegalEscalationRisk` — tenant situation in or approaching legal track
- `BelowMarketRent` — units significantly below market with no renewal planned
- `ConcentrationRisk` — over-reliance on one property, tenant type, or subsidy program

## Usage

### CLI

```bash
# Show all commands
remi --help

# JSON output for agent consumption (auto-detected when piped)
remi portfolio list --json
```

### API Server

```bash
remi serve                          # http://127.0.0.1:8000
remi serve --port 9000 --reload     # dev mode
```

## Command Groups

### Signal Layer (primary agent interface)

| Command | Description |
|---------|-------------|
| `remi onto signals` | List active signals across all managers |
| `remi onto signals --manager <id>` | Signals for a specific manager |
| `remi onto signals --severity high` | Filter by severity |
| `remi onto explain <signal-id>` | Evidence chain behind a signal |
| `remi onto infer --now` | Re-run full signal pipeline (rule + statistical) |

### Ontology (TBox + ABox queries)

| Command | Description |
|---------|-------------|
| `remi onto schema` | List all defined types and link types (TBox) |
| `remi onto schema <type>` | Describe a specific type and its properties |
| `remi onto search <type>` | Search objects of any type with filters |
| `remi onto get <type> <id>` | Get a single object by type and ID |
| `remi onto related <id>` | Find related objects via link traversal |
| `remi onto aggregate <type> <metric>` | Compute metrics across objects |
| `remi onto timeline <type> <id>` | Event history for an object |
| `remi onto codify <knowledge_type>` | Store an operational observation |

### Knowledge Base (raw graph)

| Command | Description |
|---------|-------------|
| `remi kb search` | Search the knowledge graph by entity type or text |
| `remi kb related <id>` | Traverse the raw graph from an entity |
| `remi kb summary` | Entity counts by type across namespaces |

### Properties Domain

| Command | Description |
|---------|-------------|
| `remi portfolio list` | List all portfolios |
| `remi portfolio summary <id>` | Portfolio overview with metrics |
| `remi property list` | List all properties |
| `remi property inspect <id>` | Detailed property + unit breakdown |
| `remi units list` | Search/filter units across properties |
| `remi leases list` | List leases with filters |
| `remi leases expiring` | Find leases expiring within N days |
| `remi maintenance list` | List maintenance requests |
| `remi maintenance summary` | Maintenance stats by status/category/cost |
| `remi report financial <id>` | Financial report (single period or history) |

### AI Agents

| Command | Description |
|---------|-------------|
| `remi ask portfolio "<question>"` | Ask the portfolio analyst AI |
| `remi ask property "<question>"` | Ask the property inspector AI |
| `remi ask maintenance "<question>"` | Ask the maintenance triage AI |
| `remi chat` | Interactive multi-turn chat REPL |

### Documents

| Command | Description |
|---------|-------------|
| `remi documents list` | List uploaded documents |
| `remi documents upload <path>` | Upload a CSV or Excel report |

### Framework

| Command | Description |
|---------|-------------|
| `remi app run <path>` | Execute a YAML-declared app graph |
| `remi app validate <path>` | Validate an app definition |
| `remi app list` | List registered apps |
| `remi tool list` | List all registered tools |
| `remi tool info <name>` | Describe a tool |
| `remi provider list` | List available LLM providers |
| `remi serve` | Start the FastAPI server |

## AI Agent Tools

Agents receive only the tools listed in their `app.yaml`. The full registered
set is below.

### Signal Layer Tools (primary agent entry points)

| Tool | Description |
|------|-------------|
| `onto_signals` | List active signals from all producers, optionally scoped to a manager or property |
| `onto_explain` | Retrieve the evidence chain behind a specific signal |

Signals carry `provenance` indicating their source. The `/api/v1/signals/infer`
endpoint runs the deductive pipeline. Use `/api/v1/signals/{id}/feedback` to
record outcomes.

### Hypothesis Tools (inductive knowledge discovery)

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/hypotheses/detect` | Run PatternDetector to discover candidate TBox entries |
| `GET /api/v1/hypotheses` | List hypotheses (filter by kind, status, confidence) |
| `GET /api/v1/hypotheses/{id}` | Get a single hypothesis with evidence |
| `POST /api/v1/hypotheses/{id}/confirm` | Mark hypothesis as confirmed |
| `POST /api/v1/hypotheses/{id}/reject` | Mark hypothesis as rejected |
| `POST /api/v1/hypotheses/{id}/graduate` | Promote confirmed hypothesis into live TBox |
| `POST /api/v1/hypotheses/graduate-all` | Graduate all confirmed hypotheses |

Hypotheses are candidate TBox entries — proposed signal definitions, causal
chains, or anomaly patterns. They must be confirmed before affecting the
deductive pipeline. Once graduated, they become real rules that the
`EntailmentEngine` evaluates on every subsequent run.

### Ontology Tools

| Tool | Description |
|------|-------------|
| `onto_schema` | Describe all types and link types (TBox inspection) |
| `onto_search` | Search objects of a given type with optional filters |
| `onto_get` | Get a single object by type and ID |
| `onto_related` | Traverse links from an object (depth-configurable) |
| `onto_aggregate` | Compute count/sum/avg/min/max across objects |
| `onto_timeline` | Retrieve event history for an object |
| `onto_codify_observation` | Store an LLM-derived observation (INFERRED provenance) |
| `onto_codify_causal_link` | Store a causal relationship between two entities |
| `onto_codify_policy` | Store a policy rule (restricted — TBox modification) |
| `onto_define_type` | Define a new object type (restricted — TBox modification) |

### Document Tools

| Tool | Description |
|------|-------------|
| `document_list` | List uploaded documents with metadata and report_type |
| `document_query` | Search document rows by text or column filters |

### Sandbox Tools

| Tool | Description |
|------|-------------|
| `sandbox_exec_python` | Execute Python code in an isolated sandbox |
| `sandbox_exec_shell` | Execute a shell command in the sandbox |
| `sandbox_write_file` | Write a file to the sandbox working directory |
| `sandbox_read_file` | Read a file from the sandbox working directory |
| `sandbox_list_files` | List files in the sandbox working directory |

The sandbox also contains `remi_client.py` — a stdlib-only client for the
REMI API. Sandbox scripts can query live data and codify findings:

```python
from remi_client import remi

managers = remi.search("PropertyManager")
count = remi.aggregate("Lease", "count")
signals = remi.signals(severity="high")
remi.codify("observation", {"description": "finding..."})
```

### Memory Tools

| Tool | Description |
|------|-------------|
| `memory_store` | Store a key-value pair in the agent's memory namespace |
| `memory_recall` | Retrieve a value from the agent's memory namespace |

## Agent Roles and Entry Points

### `director` (unified agent)
- **Audience:** Director (all question types)
- **Entry point:** Signal state + director's question
- **Do:** Everything — quick lookups, signal-oriented analysis, cross-referencing,
  deep sandbox-based research. All 22 tools available. Mode-switches automatically
  between fast Q&A, investigation, and deep research.
- **Sandbox:** Writes and runs Python/shell for data analysis. Static CSV
  exports and a live API client (`remi_client.py`) are available in the
  working directory. Prefer the live client for current data; use CSVs for
  bulk pandas analysis.

### `knowledge_enricher` (internal)
- **Audience:** Ingestion pipeline only
- **Entry point:** Receives ambiguous document rows as JSON input
- **Do:** Check `onto_schema` first, classify rows, propose new types via
  `onto_define_type` if needed (queued for review, not immediately live)
- **Don't use:** Any agent-facing tool

## REST API Endpoints

Base URL: `http://127.0.0.1:8000`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/portfolios` | List portfolios |
| GET | `/api/v1/portfolios/{id}/summary` | Portfolio summary |
| GET | `/api/v1/properties` | List properties |
| GET | `/api/v1/properties/{id}` | Property details |
| GET | `/api/v1/leases/expiring` | Expiring leases |
| GET | `/api/v1/maintenance` | Maintenance requests |
| GET | `/api/v1/maintenance/summary` | Maintenance summary |
| GET | `/api/v1/signals` | Active signals (all managers) |
| GET | `/api/v1/signals/{id}/explain` | Signal evidence chain |
| POST | `/api/v1/ask` | AI question |
| POST | `/api/v1/documents/upload` | Upload CSV/Excel |
| GET | `/api/v1/documents` | List documents |
| GET | `/api/v1/documents/{id}/rows` | Query document rows |
| WS | `/ws/chat` | JSON-RPC 2.0 streaming chat |

## WebSocket Chat Protocol

Connect to `ws://127.0.0.1:8000/ws/chat` and send JSON-RPC 2.0 messages:

```json
{"jsonrpc": "2.0", "method": "chat.create", "params": {"agent": "portfolio_analyst"}, "id": 1}
{"jsonrpc": "2.0", "method": "chat.send", "params": {"session_id": "...", "message": "What signals are active on Ryan's portfolio?"}, "id": 2}
```

Streaming notifications: `chat.delta`, `chat.tool_call`, `chat.tool_result`, `chat.done`.

## Output Formats

All CLI commands support dual output:

- **Human-readable** (default in TTY): Formatted tables and text
- **JSON** (`--json` flag, or auto-detected when piped): Structured data for agents

```bash
remi onto signals                    # human-readable
remi onto signals --json             # JSON
remi onto signals | jq .             # auto-JSON when piped
```

## For AI Agents

When operating REMI programmatically:

1. Always use `--json` flag for parseable output
2. Start with `remi onto signals` — understand what's currently entailed before querying facts
3. Use `remi onto explain <signal-id>` to get the evidence behind a signal
4. Use `remi onto schema` to understand what types exist before searching
5. Use `--help` at any depth to discover available commands
6. Exit code 0 = success, 1 = error
7. Codify observations with `onto_codify_observation` — provenance is `INFERRED`,
   not ground truth

## Architecture

```
domain.yaml (TBox)          Concepts, thresholds, rules, policies
      │
      ▼
EntailmentEngine            TBox rules × ABox facts → Signals
      │
      ▼
SignalStore                 Named states, evidence, severity, timestamp
      │
      ├── CLI (remi onto signals / explain / infer)
      ├── REST API (/api/v1/signals)
      └── LLM Agent (onto_signals tool — first call)

ABox stores:
  PropertyStore             Core RE entities (properties, units, leases, ...)
  KnowledgeStore            Graph entities, relationships, observations
  DocumentStore             Uploaded AppFolio reports (raw rows)

Layers:
  interfaces/               CLI + REST API + WebSocket
  application/              Use cases
  domain/                   Entities, ports, ontology types (no I/O)
  infrastructure/           Adapters: stores, tools, entailment, LLM providers
  runtime/                  Graph execution engine
  workflows/                Declarative app.yaml graphs + domain.yaml (TBox)
```

## Version

0.2.0 (Signal-layer architecture)
