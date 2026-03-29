# Incline / REMI — Architecture & Flow Diagrams

Visual reference for the system architecture, data flows, reasoning modes,
engagement model, and knowledge lifecycle.

---

## 1. Full Lifecycle: From Customer Engagement to Living Knowledge

```
╔══════════════════════════════════════════════════════════════════════════╗
║                     DISCOVERY & FORMALIZATION                          ║
║                                                                        ║
║   Customer's Domain Experts          Incline Team                      ║
║   ┌─────────────────────┐           ┌─────────────────────┐           ║
║   │ "We watch for units │           │ Facilitates,        │           ║
║   │  vacant > 30 days"  │──────────▶│ formalizes,         │           ║
║   │ "If 30% of leases   │  domain   │ challenges,         │           ║
║   │  expire at once,    │  sessions │ structures          │           ║
║   │  that's a cliff"    │           │                     │           ║
║   │ "Slow maintenance   │           │                     │           ║
║   │  causes vacancies"  │           │                     │           ║
║   └─────────────────────┘           └────────┬────────────┘           ║
║                                              │                         ║
║                                              ▼                         ║
║                                   ┌─────────────────────┐             ║
║                                   │   domain.yaml       │             ║
║                                   │   (TBox)            │             ║
║                                   │                     │             ║
║                                   │  signals:           │             ║
║                                   │    - VacancyDuration│             ║
║                                   │    - LeaseCliff     │             ║
║                                   │  thresholds:        │             ║
║                                   │    vacancy: 30 days │             ║
║                                   │  policies:          │             ║
║                                   │    - MUST: renew 90d│             ║
║                                   │  causal_chains:     │             ║
║                                   │    - slow maint →   │             ║
║                                   │      vacancy        │             ║
║                                   └────────┬────────────┘             ║
║                                            │                           ║
║              Expert reviews,               │  readable by              ║
║              corrects, extends ◀───────────┘  non-engineers            ║
║                                                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
                                     │
                                     │ TBox + data connectors
                                     ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                        SYSTEM RUNTIME                                  ║
║                                                                        ║
║  ┌─────────────────────────────────────────────────────────────────┐   ║
║  │ LAYER 1 — FACTS (ABox)                                         │   ║
║  │                                                                 │   ║
║  │  PropertyStore    KnowledgeStore    DocumentStore               │   ║
║  │  (structured)     (graph)           (uploaded reports)          │   ║
║  │                                                                 │   ║
║  │  ──── What actually happened. No interpretation. ────           │   ║
║  └──────────────────────────┬──────────────────────────────────────┘   ║
║                              │                                         ║
║                    TBox rules │ evaluated against ABox facts            ║
║                              ▼                                         ║
║  ┌─────────────────────────────────────────────────────────────────┐   ║
║  │ LAYER 2 — ENTAILMENT                                           │   ║
║  │                                                                 │   ║
║  │  ┌───────────────────┐    ┌────────────────────┐               │   ║
║  │  │  Rule Engine       │    │ Statistical        │               │   ║
║  │  │  (deduction)       │    │ Producer           │               │   ║
║  │  │                    │    │ (data-driven)       │               │   ║
║  │  │  TBox rule + fact  │    │ z-score outliers,   │               │   ║
║  │  │  → Signal          │    │ concentrations      │               │   ║
║  │  │  CERTAIN           │    │ NO RULES NEEDED     │               │   ║
║  │  └────────┬───────────┘    └─────────┬──────────┘               │   ║
║  │           │                          │                          │   ║
║  │           └──────────┬───────────────┘                          │   ║
║  │                      ▼                                          │   ║
║  │           ┌──────────────────────┐                              │   ║
║  │           │  CompositeProducer   │  dedup: earlier wins         │   ║
║  │           │  → SignalStore       │                              │   ║
║  │           └──────────────────────┘                              │   ║
║  │                                                                 │   ║
║  │  Output: named, evidenced, severity-ranked, provenance-tagged   │   ║
║  │  Signals — the system's formal claims about what is true        │   ║
║  └──────────────────────────┬──────────────────────────────────────┘   ║
║                              │                                         ║
║                              │ signals + TBox                          ║
║                              ▼                                         ║
║  ┌─────────────────────────────────────────────────────────────────┐   ║
║  │ LAYER 3 — AGENT PERCEPTION & REASONING                         │   ║
║  │                                                                 │   ║
║  │  ┌─────────────────────────────────────────────┐               │   ║
║  │  │ 1. TBox injected (categories, vocabulary)    │  PERCEPTION   │   ║
║  │  │ 2. Active signals injected (current state)   │  PERCEPTION   │   ║
║  │  │ 3. User question arrives                     │               │   ║
║  │  │ 4. LLM reasons through tools                 │  ABDUCTION    │   ║
║  │  │    - onto_explain (evidence chains)           │               │   ║
║  │  │    - onto_search / onto_aggregate             │               │   ║
║  │  │    - semantic_search (fuzzy recall)           │               │   ║
║  │  │    - sandbox (Python analysis)                │               │   ║
║  │  │ 5. Output: explanation + recommendation       │  REASONING    │   ║
║  │  └─────────────────────────────────────────────┘               │   ║
║  │                                                                 │   ║
║  │  The LLM sees through the TBox. It explains and recommends.     │   ║
║  │  It never re-derives what the engine already computed.           │   ║
║  └──────────────────────────┬──────────────────────────────────────┘   ║
║                              │                                         ║
║                              │ every step recorded                     ║
║                              ▼                                         ║
║  ┌─────────────────────────────────────────────────────────────────┐   ║
║  │ LAYER 4 — TRACE (Epistemological Audit)                        │   ║
║  │                                                                 │   ║
║  │  ENTAILMENT → PERCEPTION → LLM_CALL → TOOL_CALL → REASONING    │   ║
║  │                                                                 │   ║
║  │  Span-by-span proof that institutional expertise shaped output  │   ║
║  └─────────────────────────────────────────────────────────────────┘   ║
║                                                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## 2. The Learning Loop: How the TBox Grows Over Time

```
                    ┌──────────────────────────────────────┐
                    │          LIVE TBOX                    │
                    │  (domain.yaml + graduated entries)    │
                    │                                      │
                    │  Signals, thresholds, policies,      │
                    │  causal chains                       │
                    └───────────┬──────────────────────────┘
                                │
                   used by      │      new entries graduated in
                                │              ▲
                                ▼              │
                    ┌───────────────────┐      │
                    │ Entailment Engine │      │
                    │ (deduction)       │      │
                    └───────────────────┘      │
                                               │
         ┌─────────────────────────────────────┤
         │                                     │
         │  INDUCTIVE LOOP                     │
         │                                     │
         │  ┌─────────────────────────┐        │
         │  │ PatternDetector         │        │
         │  │                         │        │
         │  │ scans ABox data for:    │        │
         │  │  - outlier thresholds   │        │
         │  │  - correlations         │        │
         │  │  - concentrations       │        │
         │  └────────┬────────────────┘        │
         │           │                         │
         │           ▼                         │
         │  ┌─────────────────────────┐        │
         │  │ HypothesisStore         │        │
         │  │                         │        │
         │  │ PROPOSED candidates:    │        │
         │  │  confidence: 0.78       │        │
         │  │  sample_size: 142       │        │
         │  │  proposed_tbox_entry:   │        │
         │  │    {new signal def}     │        │
         │  └────────┬────────────────┘        │
         │           │                         │
         │           ▼                         │
         │  ┌─────────────────────────┐        │
         │  │ Human Review            │        │
         │  │                         │        │
         │  │  CONFIRMED ─────────────┼────────┘
         │  │  REJECTED  → archived   │
         │  │  EXPIRED   → too old    │
         │  └─────────────────────────┘
         │
         │  ABDUCTIVE LOOP
         │
         │  ┌─────────────────────────┐
         │  │ LLM Agent               │
         │  │                         │
         │  │ "I notice a pattern     │
         │  │  between maintenance    │
         │  │  delays and vacancies"  │
         │  │                         │
         │  │  → onto_codify          │──────▶ OntologyStore
         │  │    (observation)        │        (provenance: INFERRED)
         │  └─────────────────────────┘
         │
         └─────────────────────────────────────

  DISCOVERY SESSIONS (periodic, with customer)
         │
         │  "We've learned that below-market
         │   rent correlates with non-renewal.
         │   Let's add that as a causal chain."
         │
         └──────────▶ domain.yaml update
                      (provenance: SEEDED)
```

---

## 3. Three Reasoning Modes — Trust Architecture

```
 ┌────────────────────────────────────────────────────────────────────┐
 │                                                                    │
 │   DEDUCTION (Entailment Engine)                                    │
 │   ═══════════════════════════                                      │
 │                                                                    │
 │   Known law  +  Observed fact  →  Signal                           │
 │                                                                    │
 │   Provenance: DATA_DERIVED                                         │
 │   Certainty:  GIVEN RULES + DATA, THIS IS TRUE                    │
 │   Evidence:   full structured chain                                │
 │   Authority:  ██████████ highest — system acts on these            │
 │                                                                    │
 ├────────────────────────────────────────────────────────────────────┤
 │                                                                    │
 │   INDUCTION (PatternDetector)                                      │
 │   ═══════════════════════════                                      │
 │                                                                    │
 │   Observed patterns  →  Hypothesis (NOT a signal)                  │
 │                                                                    │
 │   Provenance: n/a (not yet knowledge)                              │
 │   Certainty:  PROBABILISTIC — requires confirmation                │
 │   Evidence:   statistical (z-score, correlation r, sample size)    │
 │   Authority:  ░░░░░░░░░░ none until confirmed                     │
 │                         ██████████ after graduation → LEARNED      │
 │                                                                    │
 ├────────────────────────────────────────────────────────────────────┤
 │                                                                    │
 │   ABDUCTION (LLM Agent)                                            │
 │   ═════════════════════                                            │
 │                                                                    │
 │   Observed signals  →  Best explanation + recommendation           │
 │                                                                    │
 │   Provenance: INFERRED                                             │
 │   Certainty:  PLAUSIBLE — verify before acting                     │
 │   Evidence:   natural language reasoning (traced)                  │
 │   Authority:  █████░░░░░ medium — helpful, not definitive          │
 │                                                                    │
 └────────────────────────────────────────────────────────────────────┘
```

---

## 4. Customer Engagement Model

```
  PHASE 1                PHASE 2                PHASE 3
  DISCOVERY              DEPLOYMENT             ACCUMULATION
  (weeks 1-4)            (weeks 5-8)            (ongoing)

  ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
  │              │       │              │       │              │
  │  Domain      │       │  Wire ABox   │       │  Hypotheses  │
  │  sessions    │       │  (connect    │       │  proposed    │
  │  with        │──────▶│  their       │──────▶│  from live   │
  │  experts     │       │  systems)    │       │  data        │
  │              │       │              │       │              │
  │  Capture:    │       │  Deploy:     │       │  Review:     │
  │  - signals   │       │  - engine    │       │  - confirm   │
  │  - thresholds│       │  - agent     │       │  - reject    │
  │  - policies  │       │  - traces    │       │  - calibrate │
  │  - causality │       │  - dashboard │       │              │
  │              │       │              │       │  Periodic    │
  │  Output:     │       │  Output:     │       │  sessions:   │
  │  domain.yaml │       │  live system │       │  "is 30 days │
  │  (v1 TBox)   │       │  producing   │       │  still right │
  │              │       │  signals     │       │  for chronic  │
  │              │       │              │       │  vacancy?"   │
  └──────────────┘       └──────────────┘       └──────────────┘
                                                       │
                                                       ▼
                                                TBox v2, v3, v4...
                                                (living expertise)


  VALUE DELIVERED AT EACH PHASE:

  Phase 1: "We now have a written, reviewable artifact of what
            our best people know. That alone is valuable."

  Phase 2: "The system watches everything and tells us what
            matters before we ask. With evidence."

  Phase 3: "The system is discovering patterns we didn't know
            about and getting smarter in ways we can inspect."
```

---

## 5. Provenance — The Trust Gradient

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │  CORE           ████████████████████████████  built into system │
  │  SEEDED         ██████████████████████████░░  from domain.yaml  │
  │  DATA_DERIVED   ████████████████████████░░░░  engine computed   │
  │  USER_STATED    ██████████████████████░░░░░░  human asserted    │
  │  LEARNED        ████████████████████░░░░░░░░  confirmed hypo    │
  │  INFERRED       ██████████████░░░░░░░░░░░░░░  LLM guessed      │
  │                                                                 │
  │  ◀──────────── increasing trust ────────────▶                   │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘

  Every fact, signal, and codified observation in the system carries
  one of these tags. The user always knows: how was this produced,
  and how much should I trust it?
```

---

## 6. The Napkin Diagram

The one you draw at dinner to explain the whole thing.

```
       THEIR EXPERTS               THEIR DATA
       (what things mean)          (what happened)
              │                         │
              ▼                         ▼
         ┌─────────┐             ┌───────────┐
         │  TBox   │             │   ABox    │
         │  (YAML) │             │  (stores) │
         └────┬────┘             └─────┬─────┘
              │                        │
              └───────────┬────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │    ENTAILMENT   │
                 │    ENGINE       │
                 │                 │
                 │  rules + facts  │
                 │  = signals      │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │    SIGNALS      │
                 │                 │
                 │  named          │
                 │  evidenced      │
                 │  trusted        │
                 └────────┬────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     ┌─────────────────┐    ┌─────────────────┐
     │   DASHBOARD     │    │   AI AGENT      │
     │   (no AI needed │    │   (explains,    │
     │   to see what   │    │   connects,     │
     │   matters)      │    │   recommends)   │
     └─────────────────┘    └─────────────────┘
                                    │
                                    ▼
                          ┌─────────────────┐
                          │   TRACE         │
                          │   (prove it)    │
                          └─────────────────┘
```

**The key insight this communicates:** The AI is not the product. The signals
are the product. The AI just explains them. The real value is in the box that
says "their experts" flowing into the box that says "TBox." Everything else is
infrastructure to make that formalized expertise operational at scale.

---

## 7. Framework vs. Product Boundary

```
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  INCLINE (framework — domain-agnostic)                         │
  │                                                                │
  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
  │  │  Ontology     │ │  Entailment  │ │  Hypothesis  │          │
  │  │  System       │ │  Engine      │ │  Pipeline    │          │
  │  └──────────────┘ └──────────────┘ └──────────────┘          │
  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
  │  │  Agent Loop   │ │  Trace Layer │ │  Sandbox     │          │
  │  │  (AgentNode)  │ │  (SpanKind)  │ │  (isolated)  │          │
  │  └──────────────┘ └──────────────┘ └──────────────┘          │
  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
  │  │  Vectors      │ │  Tools       │ │  Graph       │          │
  │  │  (retrieval)  │ │  (registry)  │ │  Runtime     │          │
  │  └──────────────┘ └──────────────┘ └──────────────┘          │
  │                                                                │
  │  Litmus test: "Would this exist if we swapped verticals?"      │
  │               If yes → Incline.                                │
  │                                                                │
  ├────────────────────────────────────────────────────────────────┤
  │                                                                │
  │  PRODUCT (e.g. REMI — real estate)                             │
  │                                                                │
  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
  │  │  domain.yaml  │ │  Property    │ │  Director    │          │
  │  │  (TBox)       │ │  Store       │ │  Agent       │          │
  │  │  12 signals   │ │  (ABox)      │ │  (workflow)  │          │
  │  └──────────────┘ └──────────────┘ └──────────────┘          │
  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
  │  │  Type         │ │  RE-specific │ │  RE API      │          │
  │  │  Bindings     │ │  Evaluators  │ │  + CLI       │          │
  │  └──────────────┘ └──────────────┘ └──────────────┘          │
  │                                                                │
  │  If no → product.                                              │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
```

---

## Further Reading

- **[PHILOSOPHY.md](PHILOSOPHY.md)** — The full thesis on knowledge,
  intelligence, and structured perception
- **[VISION.md](VISION.md)** — Pitches and shorthand at every level
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Technical architecture details
- **[INCLINE.md](INCLINE.md)** — Framework package boundary and how to add
  a new domain
