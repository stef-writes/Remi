# REMI Architecture

## What This System Is

REMI is an AI platform for directors of property management. A director oversees
multiple property managers, each running portfolios of 15–40 properties. Her job
is not to manage properties — it is to manage managers. Her core question, every
day, is:

> **Which of my managers needs my attention, and why?**

REMI answers that question before she asks it. It monitors the book of business,
detects situations that require the director's judgment, and provides an AI agent
that can explain, investigate, and recommend — grounded in the actual data and
the domain expertise of property management.

---

## Incline and REMI

**Incline** is the domain-agnostic AI infrastructure underneath — the graph
runtime, ontology system, entailment engine, signal framework, hypothesis
pipeline, LLM providers, sandbox, trace layer, and tool system. It is the
reusable IP.

**REMI** is the first product built on Incline, proving the framework in the
property management vertical. Everything RE-specific — PropertyStore, the 12
PM signals in domain.yaml, the director agent, the AppFolio ingestion pipeline
— is REMI. Everything else is Incline.

See `INCLINE.md` for the full framework architecture and package boundary.

---

## TBox and ABox — The Foundational Distinction

These terms come from Description Logic, the formal underpinning of knowledge
representation systems. They describe two fundamentally different kinds of
knowledge.

### TBox — Terminological Box

The TBox defines **what kinds of things exist and what they mean**. It is the
vocabulary and the rules of the domain. It answers: *what is a ChronicVacancy?
What counts as a LeaseExpirationCliff? What does it mean for a manager to be
underperforming?*

The TBox is not data. It is **institutional expertise, formalized**. It contains:

- **Concept definitions** — named domain states with human-readable descriptions
- **Inference rules** — conditions under which a concept is entailed to be true
- **Thresholds** — the numeric calibrations that define normal vs. alarming
- **Policies** — obligations that should follow from certain conditions
- **Causal chains** — relationships between domain states (slow maintenance
  causes extended vacancy)

In REMI, the TBox lives in `src/remi/workflows/domain.yaml`. It is the single
file a domain expert should read, correct, and extend. No code change required
to update a threshold or add a new signal.

### ABox — Assertion Box

The ABox contains **individual facts asserted about the world**. It answers:
*what actually happened? What is the current state of this specific lease, unit,
tenant, property?*

The ABox is the data. In REMI:

- `PropertyStore` — the structured ABox for core RE entities (properties, units,
  leases, tenants, maintenance requests)
- `KnowledgeStore` — the graph ABox for relationships, observations, and
  dynamically discovered entities
- Uploaded AppFolio reports — raw ABox assertions ingested from the real world

### Why the Distinction Matters

Without a TBox, the system has data but no meaning. The LLM is forced to
reconstruct domain expertise from scratch on every query — which is slow,
inconsistent, and doesn't accumulate.

Without an ABox, the TBox has rules but nothing to apply them to.

The **Entailment Engine** combines them: it evaluates TBox rules against ABox
facts and produces **Signals** — named, evidenced, severity-ranked states that
represent what is currently true about the director's world.

---

## The Four Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 1 — FACTS (ABox)                                          │
│                                                                  │
│  PropertyStore: properties, units, leases, tenants, maintenance  │
│  KnowledgeStore: relationships, graph entities, observations     │
│  DocumentStore: uploaded AppFolio reports (raw rows)             │
│                                                                  │
│  What actually happened. No interpretation.                      │
└────────────────────────┬─────────────────────────────────────────┘
                         │ evaluated against
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 2 — DOMAIN (TBox)                                         │
│                                                                  │
│  domain.yaml: concepts, thresholds, rules, policies, causality   │
│  bootstrap.py: loads TBox into the ontology at startup           │
│                                                                  │
│  What things mean in this business. Domain expertise formalized. │
│  Editable by domain experts without touching code.               │
└────────────────────────┬─────────────────────────────────────────┘
                         │ produces
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 3A — SIGNAL PIPELINE (Deductive — known physics)          │
│                                                                  │
│  CompositeProducer → merges SignalProducers:                     │
│    ├── RuleBasedProducer (EntailmentEngine) — TBox rules         │
│    └── StatisticalProducer — z-score outliers, concentrations    │
│                                                                  │
│  SignalStore: named signals with evidence, severity, provenance  │
│  FeedbackStore: tracks outcomes (acted_on, dismissed, etc.)      │
│  MutableDomainOntology: static TBox + graduated learned entries  │
│                                                                  │
│  LAYER 3B — HYPOTHESIS PIPELINE (Inductive — discovering physics)│
│                                                                  │
│  PatternDetector → scans ABox data for patterns, proposes:       │
│    ├── Threshold hypotheses → candidate SignalDefinitions         │
│    ├── Correlation hypotheses → candidate CausalChains            │
│    └── Anomaly patterns → codified observations                  │
│                                                                  │
│  HypothesisStore: candidate TBox entries awaiting review         │
│  HypothesisGraduator: confirmed → live TBox entries              │
│                                                                  │
│  Lifecycle: PROPOSED → CONFIRMED → graduated into TBox           │
│             PROPOSED → REJECTED  → archived                      │
└──────┬──────────────────────────┬────────────────────────────────┘
       │ navigated by             │ displayed by
       ▼                          ▼
┌─────────────────────┐  ┌───────────────────────────────────────┐
│  LAYER 4A — CLI     │  │  LAYER 4B — FRONTEND                  │
│                     │  │                                        │
│  remi onto signals  │  │  Signals dashboard — no conversation   │
│  remi onto explain  │  │  needed to see what matters today      │
│  remi onto infer    │  │  Click a signal → agent investigates   │
│  remi onto codify   │  └───────────────────────────────────────┘
│                     │
│  + all existing     │
│  domain/doc/sandbox │
│  commands           │
└─────────┬───────────┘
          │ tools available to
          ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 4C — LLM AGENT (Unified Director)                         │
│                                                                  │
│  Receives: signal + evidence + director's question               │
│  Does: explain, connect, recommend, codify, analyze data         │
│  Modes: quick answer → investigation → deep research             │
│  Sandbox: writes and runs Python/shell for data science tasks    │
│  Never: recomputes what the entailment engine already knows      │
│  Grows: the TBox via codified observations (with provenance)     │
└────────────────────────┬─────────────────────────────────────────┘
                         │ every step recorded by
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 5 — TRACES (Reasoning Observability)                       │
│                                                                  │
│  TraceStore: hierarchical spans with SpanKind categories         │
│  Captures: entailment → perception → LLM → tools → reasoning    │
│  CLI: remi trace show <id> renders the full reasoning tree       │
│  Agent tools: trace_show, trace_list (metacognitive inspection)  │
│  Logs: trace_id + span_id auto-injected via contextvars          │
│                                                                  │
│  The proof that institutional expertise shapes agent perception. │
└──────────────────────────────────────────────────────────────────┘
```

---

## The Unified Agent Model

REMI uses a single conversational agent — the **director** — that adapts its
approach to the question. This is the same architecture used by Claude, ChatGPT,
and Gemini: one model, one tool set, behavior driven by the system prompt.

### How mode-switching works

The agent has three modes, selected automatically based on the question:

| Mode | Trigger | Tool calls | Example |
|------|---------|-----------|---------|
| **Quick answer** | Known-shape question | 1-3 | "How is Marcus doing?" |
| **Investigation** | Cross-referencing needed | 3-8 | "Compare vacancy rates across managers" |
| **Deep research** | Open-ended / analytical | 5-20 | "Is there a seasonal pattern in vacancies?" |

In deep research mode, the agent follows a structured workflow:
clarify → plan → execute (sandbox) → observe → synthesize.

### Why one agent, not specialists

Previously REMI had 4 specialist agents (portfolio_analyst, property_inspector,
maintenance_triage, director). These were consolidated because:

1. **Routing is a solved problem.** A well-prompted agent with all tools selects
   the right approach itself. Separate agents add routing complexity without
   adding capability.
2. **Context is lost at boundaries.** When the director asks about a property
   and then about its manager, a specialist hand-off loses the thread.
3. **Maintenance burden.** 4 YAMLs with overlapping tools and prompts means
   4 places to update when a tool changes.

---

## Sandbox — Isolated Code Execution

The sandbox gives the agent the ability to write and run Python/shell code
for analysis that goes beyond what tool calls can express.

### Architecture

```
┌─────────────────────────────────────────────────┐
│  Agent (LLM loop)                                │
│                                                  │
│  sandbox_exec_python(code="...")                  │
│  sandbox_write_file(filename, content)           │
│  sandbox_read_file(filename)                     │
│  sandbox_list_files()                            │
└──────────────────┬──────────────────────────────┘
                   │ tool call
                   ▼
┌─────────────────────────────────────────────────┐
│  LocalSandbox                                    │
│                                                  │
│  - Each chat session gets its own temp directory │
│  - Python runs in a subprocess with restricted   │
│    environment (no host filesystem, no network)  │
│  - Timeouts enforced per execution               │
│  - Dangerous commands blocked                    │
└──────────────────┬──────────────────────────────┘
                   │ on session start
                   ▼
┌─────────────────────────────────────────────────┐
│  SandboxSeeder                                   │
│                                                  │
│  Exports PropertyStore + SignalStore data as:    │
│  - managers.csv, portfolios.csv, properties.csv  │
│  - units.csv, leases.csv, tenants.csv            │
│  - maintenance.csv, signals.json                 │
│  - README.txt (file schemas)                     │
└─────────────────────────────────────────────────┘
```

### Live Ontology Access from Sandbox

The sandbox is not limited to static CSV snapshots. At session start, the
`SandboxSeeder` writes a `remi_client.py` module into the working directory —
a stdlib-only Python client that calls the REMI API over HTTP.

Agent scripts use it to query **live** data and codify findings back:

```python
from remi_client import remi

managers = remi.search("PropertyManager")
signals = remi.signals(severity="high")
count = remi.aggregate("Lease", "count")
remi.codify("observation", {"description": "seasonal vacancy pattern"})
```

This closes the loop: sandbox analysis → codified knowledge → updated
ontology → re-derived signals. The sandbox becomes a first-class participant
in the ontology, not a disconnected CSV playground.

The `RemoteOntologyStore` class (in `infrastructure/ontology/remote.py`)
implements the full `OntologyStore` ABC over HTTP, making it a typed, drop-in
replacement for `BridgedOntologyStore`. Any code that takes an `OntologyStore`
works identically whether backed by local stores or by HTTP calls to a
running REMI server.

### Trust model

The sandbox protects real data through subprocess isolation:

- Agent code runs in a **separate process** with no references to REMI's
  in-process stores
- The working directory is a **temp directory** — agent code cannot read or
  write the host filesystem
- The sandbox client (`remi_client.py`) talks to the API server — reads and
  writes go through the ontology layer with full provenance tracking
- Static CSV exports remain available for bulk pandas analysis
- Dangerous commands (sudo, curl, network tools) are blocked

---

## Tool Inventory

26 tools registered, organized by module:

### Ontology (12 tools)
Core domain querying and knowledge management.

| Tool | Purpose |
|------|---------|
| `onto_signals` | List active entailed signals |
| `onto_explain` | Get evidence behind a signal |
| `onto_search` | Search entities by type and filters |
| `onto_get` | Get a single entity by ID |
| `onto_related` | Traverse entity relationships |
| `onto_aggregate` | Aggregate metrics (count, sum, avg, group) |
| `onto_schema` | Inspect the ontology schema (TBox types) |
| `onto_timeline` | Get temporal events for an entity |
| `onto_codify_observation` | Assert a new observation |
| `onto_codify_policy` | Define a new policy rule |
| `onto_codify_causal_link` | Define a cause-effect relationship |
| `onto_define_type` | Define a new entity type |

### Documents (2 tools)
Access to uploaded reports and documents.

| Tool | Purpose |
|------|---------|
| `document_list` | List uploaded documents |
| `document_query` | Query document rows with filters |

### Vectors (2 tools)
Semantic search across all embedded entities.

| Tool | Purpose |
|------|---------|
| `semantic_search` | Find entities by meaning |
| `vector_stats` | Embedding statistics |

### Sandbox (5 tools)
Isolated code execution for data analysis.

| Tool | Purpose |
|------|---------|
| `sandbox_exec_python` | Run Python code |
| `sandbox_exec_shell` | Run shell commands |
| `sandbox_write_file` | Write a file to sandbox |
| `sandbox_read_file` | Read a file from sandbox |
| `sandbox_list_files` | List sandbox files |

### Trace (3 tools)
Metacognitive inspection of reasoning history.

| Tool | Purpose |
|------|---------|
| `trace_list` | List recent traces |
| `trace_show` | Show full span tree |
| `trace_spans` | Flat span list |

### Memory (2 tools)
Cross-session memory persistence.

| Tool | Purpose |
|------|---------|
| `memory_store` | Store a memory |
| `memory_recall` | Recall memories |

---

## The Twelve Signals

These are the domain concepts the director reasons in. The entailment engine
detects them. The LLM explains and acts on them.

### Portfolio Health Signals

| Signal | What It Means | Horizon |
|--------|--------------|---------|
| `OccupancyDrift` | A manager's occupancy declining over 2+ consecutive periods. Direction matters more than level. | Trailing 90 days |
| `DelinquencyConcentration` | Delinquency rate exceeds threshold of gross rent roll, or same tenants delinquent month after month. | Current |
| `LeaseExpirationCliff` | >30% of a manager's leases expire within 60 days with no renewals underway. | Next 60 days |
| `VacancyDuration` | Units vacant beyond the market-normal window (default: 30 days). Signals pricing, condition, or leasing failure. | Current |
| `MaintenanceBacklog` | Open work orders aging without resolution, especially in occupied units. | Current |

### Manager Performance Signals

| Signal | What It Means | Horizon |
|--------|--------------|---------|
| `OutlierPerformance` | A manager significantly below peer group on key metrics. Coaching signal, not crisis. | Current period |
| `PerformanceTrend` | A manager who was fine is now declining. Or struggling and now improving. Direction matters. | Trailing 60 days |
| `CommunicationGap` | Situations visible in the data that the director hasn't been told about. | Current |

### Operational Signals

| Signal | What It Means | Horizon |
|--------|--------------|---------|
| `PolicyBreach` | A required action didn't happen: renewal offer not sent, notice not filed, make-ready overdue. | Event-driven |
| `LegalEscalationRisk` | A tenant situation approaching or in a legal track requiring director awareness. | Current |
| `BelowMarketRent` | Units significantly below current market rent, no renewal conversation planned. Revenue leakage. | Current |
| `ConcentrationRisk` | A single property, tenant type, or subsidy program is too large a share of a manager's portfolio. | Current |

---

## The LLM's Role — Precisely

The LLM does **not** detect signals. The entailment engine does that. The LLM's
job is **abductive reasoning** — inference to the best explanation given the
signal and its evidence.

```
Deduction  →  EntailmentEngine   →  "There IS a LeaseExpirationCliff"
                                    (certain, rule-based, pre-computed)
                                    Uses: known laws from TBox (static + graduated)

Induction  →  PatternDetector   →  "days_vacant has outliers at 4.2σ —
                                    propose a threshold signal definition"
                                    (probabilistic, requires confirmation)
                                    Produces: Hypothesis, NOT Signal

Abduction  →  LLM               →  "The cliff is likely unmanaged because
                                    three of the five expiring tenants have
                                    been month-to-month for 2+ years, which
                                    suggests the manager avoids renewal
                                    conversations on long-tenure tenants"
                                    (probable, context-dependent, human-language)
```

The LLM uniquely contributes:

1. **Reading unstructured text** — delinquency notes, maintenance descriptions,
   tenant histories. The entailment engine cannot parse "tenant passed away,
   wife is living there, unit needs a lot of work." The LLM can.

2. **Connecting signals** — a maintenance backlog and a vacancy duration signal
   on the same portfolio are probably related. The LLM forms that hypothesis.

3. **Recommending action** — not just "there is a problem" but "this specific
   tenant has been on a payment plan for 3 years with the same balance; this is
   a decision point, not a collections call."

4. **Data science** — statistical analysis, trend detection, and pattern
   recognition via sandbox code execution. The LLM writes and runs Python
   scripts to answer questions the pre-built tools can't.

5. **Translating to human language** — the director reads prose, not JSON.

The LLM never recomputes what the entailment engine already knows.

---

## The CLI as Epistemological Interface

The CLI is the formal language through which agents (human and LLM) make
epistemic claims about the world. Every command is an epistemic act:

```bash
remi onto signals --manager <id>     # What is currently entailed to be true?
remi onto explain <signal-id>        # What evidence justifies this state?
remi onto infer --now                # Re-evaluate all rules against current facts
remi onto codify observation ...     # Assert a new piece of knowledge (USER_STATED)
remi onto schema                     # Inspect the TBox (what concepts exist?)
```

The CLI grammar is stable across domains. Only the TBox changes. An LLM agent
that knows this grammar can operate in any domain the framework is applied to,
because it has already learned the epistemological structure: observe, assert,
derive, explain, act.

---

## The Ontology as Institutional Memory

The TBox accumulates domain expertise over time:

- Thresholds the director calibrates from her experience
- Causal chains observed across the portfolio ("below-market rent leads to
  missed renewal conversations leads to unexpected vacancies")
- Policies established from repeated situations
- Signals the LLM discovered and codified

Every `onto_codify observation` call is a potential TBox addition. The
provenance system (`CORE`, `SEEDED`, `DATA_DERIVED`, `USER_STATED`, `INFERRED`, `LEARNED`)
tracks how each piece of knowledge entered the system and how much trust it
deserves.

The ontology is not a static schema. It is a **living epistemic artifact** —
the formalized, versioned, reviewable expertise of this director and this
domain.

---

## Agent Roles

### `director`
**Audience:** Director (all question types)
**Entry point:** Signal state + director's question
**Primary job:** Everything — from quick lookups to deep research
**Unique capability:** Mode-switching between fast Q&A, investigation, and
deep sandbox-based research. All 22 tools available. Writes and runs Python
for analysis that goes beyond pre-built tool capabilities.

### `knowledge_enricher`
**Audience:** Internal (ingestion pipeline)
**Entry point:** Ambiguous document rows
**Primary job:** Classify rows into typed ontology entities; extend TBox if new
types are discovered
**Unique capability:** TBox-aware classification — uses `onto_schema` before
deciding on entity types, extends the ontology rather than forcing unknown data
into existing types

---

## Workflow Files

```
src/remi/workflows/
  domain.yaml                    # TBox — domain expertise as YAML
  director/app.yaml              # The unified conversational agent
  knowledge_enricher/app.yaml    # Internal ingestion agent
```

---

## The Trace Layer — Observability as Proof

The trace layer captures the full reasoning chain: data entered → entailment
engine fired → signals produced → agent perceived through TBox → agent called
tools → agent reasoned → output produced. Every step is a **Span** in a
hierarchical **Trace**.

### SpanKind — Epistemological Categories

Each span is categorized by the *kind of cognitive act* it represents:

| SpanKind | What it captures |
|----------|-----------------|
| `ENTAILMENT` | The entailment engine evaluating a TBox rule against ABox facts |
| `PERCEPTION` | The agent receiving its world model (TBox injection, active signals) |
| `LLM_CALL` | A raw LLM request/response (model, tokens, latency) |
| `TOOL_CALL` | The agent invoking a tool (name, arguments, result) — includes sandbox |
| `REASONING` | The agent's final output (signals referenced, recommendations made) |
| `SIGNAL` | A signal produced, retired, or referenced |
| `GRAPH` | Graph-level execution (app run, module orchestration) |
| `MODULE` | A single module executing within a graph |

### Trace CLI

```bash
remi trace list                           # Recent traces
remi trace show <trace-id>                # Full span tree, human-readable
remi trace show <trace-id> --kind entailment  # Filter to entailment spans
remi trace spans <trace-id>               # Flat span list
```

### Agent Self-Inspection

Agents have access to `trace_list`, `trace_show`, and `trace_spans` tools,
enabling metacognitive reasoning: "In my previous analysis, I detected a
LeaseExpirationCliff based on the 30% threshold. Here's the evidence chain..."

### Structured Log Correlation

Every structlog event automatically includes `trace_id` and `span_id` when
a trace is active, so log output correlates directly with the span tree.

### Why This Matters

Without the trace layer, the claim that "the TBox shapes the agent's
perception" is unverifiable. With it, you can literally watch: the TBox
was injected → these signals were active → the agent referenced them →
the recommendation followed from the domain rules. The trace is both the
**proof mechanism** and the **trust infrastructure**.

---

## Provenance Tags (Epistemic Classification)

Every fact, signal, and codified observation carries a provenance tag:

| Tag | Meaning | Trust |
|-----|---------|-------|
| `CORE` | Defined by the system at build time | Highest |
| `SEEDED` | Loaded at bootstrap from `domain.yaml` | High |
| `DATA_DERIVED` | Computed from ABox facts by entailment | High (rule-dependent) |
| `USER_STATED` | Asserted by the director or a manager | High (but overridable) |
| `INFERRED` | Produced by the LLM via abductive reasoning | Medium (verify before acting) |

The distinction matters: a `DATA_DERIVED` signal is certain given the rules. An
`INFERRED` observation from the LLM is a hypothesis that should be presented as
such.

---

## Version

Architecture version: 5.0 (Incline/REMI boundary established)
Document date: 2026-03-29
