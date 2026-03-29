# Incline — Vision & Pitch

How we describe what we do, at every level of compression.

---

## The One-Liner

**We turn your institutional expertise into a machine-readable knowledge system
that tells an AI what to see, what to say, and what to prove.**

---

## The One Phrase (for technical people)

**Structured perception over declarative domain knowledge, with formal
entailment, provenance-tagged outputs, and a bounded LLM.**

Or shorter: **We give the AI a TBox so it doesn't have to improvise your
expertise.**

---

## The Elevator Pitch (30 seconds)

Every company has domain expertise — the rules, thresholds, causal
relationships, and policies that their best people carry in their heads. We
formalize that expertise into a structured TBox (a YAML file domain experts
can read and edit), run it against their live data through an entailment engine
that produces named, evidenced signals, and give an LLM agent that *perceives
through those signals* instead of improvising from scratch. The AI explains and
recommends; it doesn't detect or decide. Every step is traced and
provenance-tagged. The expertise accumulates in the system, not in any person's
head.

---

## The Technical Pitch (2 minutes)

The architecture has five commitments:

**1. TBox/ABox separation.** Domain expertise (signal definitions, thresholds,
policies, causal chains) lives in YAML — the TBox. Operational facts (entities,
records, uploaded reports) live in typed stores — the ABox. These are authored
by different people, versioned independently, and combined by a formal engine.
Most AI systems flatten both into embeddings. We don't.

**2. Entailment, not vibes.** A rule engine evaluates TBox rules against ABox
facts and produces Signals — named, severity-ranked, evidence-carrying claims
about what's currently true. The LLM receives these signals as pre-computed
perception. It never re-derives what the engine already knows. Deduction
(engine), induction (pattern detector → hypotheses → human confirmation →
graduated rules), and abduction (LLM) have separate lanes with separate trust
levels.

**3. Provenance on everything.** Every claim carries a tag: `CORE`, `SEEDED`,
`DATA_DERIVED`, `USER_STATED`, `INFERRED`, `LEARNED`. The system knows the
difference between what it computed, what a human told it, and what the LLM
guessed. So does the user.

**4. Traces as proof.** Every reasoning chain is a hierarchical span tree with
epistemological categories — entailment, perception, LLM call, tool call,
reasoning. You can follow any output back to the exact rule, data, and model
interaction that produced it. Unverifiable claims of intelligence are worthless.

**5. Domain-agnostic framework.** The framework (Incline) provides the ontology
system, entailment engine, hypothesis pipeline, agent loop, trace layer,
sandbox, vectors, and tools. The product provides six things: a TBox, a domain
store, agent workflows, type bindings, evaluators, and domain interfaces. Swap
the TBox and the store, you have a new vertical.

---

## The Business Pitch

The valuable part is not the software. The valuable part is the **TBox** — and
the TBox comes from *working closely with the customer's domain experts*.

What we actually sell:

- **We sit with your best people and formalize what they know.** The signals
  they watch for. The thresholds they've calibrated from experience. The causal
  chains they've observed. The policies that should be enforced. We turn that
  into a `domain.yaml` they can read, correct, and own.

- **We wire it to your data.** Your existing systems become the ABox. The
  entailment engine runs your experts' rules against your live operational data
  and produces signals — automatically, continuously, with evidence.

- **We give you an AI that thinks like your institution.** Not a generic
  chatbot. An agent that perceives through your categories, references your
  signals by name, cites your data, and proves how it arrived at every
  recommendation.

- **The expertise compounds.** Every threshold calibration, every codified
  observation, every graduated hypothesis makes the TBox richer. The system
  gets smarter over time — not through opaque model updates, but through
  reviewable, versioned knowledge your team controls.

The close relationship isn't overhead. It's the product. The domain expertise is
the moat — not the model, not the infra. The companies that let us formalize
their institutional knowledge get an AI system that actually knows their
business. The ones using generic AI are rebuilding expertise from scratch on
every query.

---

## The Napkin Version

```
Your experts know things  →  We formalize it (YAML TBox)
Your systems have data    →  We connect it (ABox stores)
Engine applies rules      →  Signals (named, evidenced, trusted)
LLM sees through signals  →  Explains, connects, recommends
Everything traced         →  Prove every claim
Expertise accumulates     →  System gets smarter, people can leave
Framework is generic      →  TBox is the variable, not the code
```

---

## Key Differentiators (vs. the rest of the market)

| What others do | What we do |
|----------------|-----------|
| Embed everything into vectors, prompt the LLM | Separate TBox (meaning) from ABox (facts), combine through formal entailment |
| LLM detects problems and explains them | Entailment engine detects; LLM explains. Different systems, different trust levels |
| "AI-powered insights" (unverifiable) | Named signals with evidence chains and span-level traces |
| Fine-tune or RAG for domain knowledge | Declarative YAML TBox editable by domain experts, no code needed |
| Static system, same capability on day 1 and day 100 | Hypothesis pipeline discovers patterns, graduates confirmed ones into live rules |
| Model is the product | Institutional expertise is the product; model is the reader |

---

## Further Reading

- **[PHILOSOPHY.md](PHILOSOPHY.md)** — The full thesis on knowledge,
  intelligence, and structured perception
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Technical architecture of the
  system
- **[INCLINE.md](INCLINE.md)** — Framework vs. product boundary
- **[DIAGRAMS.md](DIAGRAMS.md)** — Visual architecture and flow diagrams
