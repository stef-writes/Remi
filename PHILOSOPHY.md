# Structured Perception: A Theory of Knowledge for Artificial Intelligence

**On the philosophy, architecture, and practice of building AI systems that actually know things**

---

## I. The Problem With Intelligent Machines

The most common question people ask about AI is whether it's truly intelligent.
This is the wrong question. Intelligence, detached from structure, is noise. A
mind — human or artificial — that processes the world without categories, without
a vocabulary for what matters, without the accumulated judgment of the institution
it serves, will produce answers that are fluent, plausible, and untrustworthy. It
will reinvent expertise from scratch on every query. It will be right often enough
to be dangerous and wrong in ways that are invisible until the damage is done.

The question is not whether the machine is intelligent. The question is: **does it
know anything?**

Knowledge is not a property of processors or parameters. Knowledge is a
relationship between a structured perceiver and a structured world, mediated by
rules the perceiver can inspect and the world can validate. This paper is about
what that means — philosophically and practically — and about the software
architecture we built to prove it works.

---

## II. What We Mean By Knowledge

### The Kantian Inheritance

Immanuel Kant's central insight was that the mind is not a blank surface on which
reality writes. The mind brings *structure* to experience. Categories like
causality, quantity, and quality are not discoveries we make in the world; they
are the preconditions that make experience of the world possible in the first
place. We do not perceive "a cause" lying on the ground. We perceive raw sense
data and our mind structures it *as* causal.

This insight, universally accepted in cognitive science and almost universally
ignored in AI engineering, is the foundation of everything we build. An LLM does
not perceive "a delinquency problem" in a rent roll. It perceives tokens. If you
give it raw data, it must reconstruct the categories — what counts as delinquent,
what threshold separates normal from alarming, what the institutional norms are —
every single time. This reconstruction is slow, inconsistent, and invisible. The
model has no stable categories. It improvises them.

Our architecture gives the model categories. Before the LLM processes a single
user message, the system injects a **TBox** — a terminological box, borrowed from
Description Logic — containing the domain's signal definitions, thresholds,
policies, and causal chains. This is not "context." This is the transcendental
structure that makes perception possible. The model doesn't see the world and
then decide what matters. It sees the world *through* the institution's
categories, or it doesn't see it at all.

We label this step `PERCEPTION` in our trace layer. Not "prompt setup." Not
"context injection." Perception — because that is what it is: the moment the
agent's phenomenal world is constituted.

### The Wittgensteinian Turn

Kant tells us that perception requires structure. Wittgenstein tells us where
that structure comes from: not from the mind in isolation, but from **forms of
life** — the shared practices, vocabularies, and rules of a community.

Late Wittgenstein argued that meaning is not a private mental state and not a
correspondence between words and objects. Meaning is use within a language game.
"ChronicVacancy" does not refer to some Platonic object in the world. It *means*
something because it exists within the language game of property management — it
has a threshold (30 days), a severity level, an entity type it applies to, an
inference rule that determines when it fires. Its meaning is exhausted by its
role in the system.

Our TBox, expressed as a YAML file called `domain.yaml`, is a formalized
language game. The opening comment reads: *"What things mean in this business."*
Not what things *are*. What they *mean*. A different business — healthcare,
logistics, finance — would have a different TBox: different signals, different
thresholds, different causal chains, different policies. The underlying framework
would be identical, because the framework provides the capacity for language
games, not any particular one.

This is why the TBox is YAML and not code. Wittgenstein insisted that the rules
of a language game must be accessible to its participants. If domain knowledge is
locked in Python methods, only engineers can read it. If it's in YAML with
human-readable descriptions, the domain expert — the actual participant in the
form of life — can inspect, correct, and extend it without writing a line of
code. The institution's knowledge is *public*, not hidden in implementation
details.

### Beyond Justified True Belief

Edmund Gettier demonstrated in 1963 that justified true belief is not sufficient
for knowledge. You can believe something, have justification for believing it,
and the belief can be true — and yet you don't *know* it, because the
justification doesn't actually connect to the truth in the right way. You can be
right by accident.

This problem is not academic for AI systems. It is the central failure mode. An
LLM might say "this manager has a delinquency problem" and be correct — the
delinquency rate is 12%. But the LLM might have arrived at that conclusion by
misinterpreting a maintenance report, pattern-matching on the word "overdue" in
a context that had nothing to do with rent. The claim is true. The justification
exists. But the justification doesn't connect to the truth through the right
chain. That's a Gettier case. In production, it's a liability.

Our architecture makes Gettier cases structurally visible through two mechanisms:

**Provenance.** Every claim in the system carries a tag indicating how it was
produced and how much trust it deserves. A signal produced by the entailment
engine is `DATA_DERIVED` — the chain runs from TBox rule through PropertyStore
query through threshold comparison to output. The justification and the truth
are connected by the same auditable chain. A claim produced by the LLM's
abductive reasoning is tagged `INFERRED` — medium trust, verify before acting.
The system is telling you: *this might be right for the wrong reasons.*

| Provenance | Origin | Trust |
|------------|--------|-------|
| `CORE` | Built into the system | Highest |
| `SEEDED` | Loaded from the TBox at startup | High |
| `DATA_DERIVED` | Computed by the entailment engine from rules + facts | High |
| `USER_STATED` | Asserted by a human operator | High (overridable) |
| `INFERRED` | Produced by the LLM via abductive reasoning | Medium |
| `LEARNED` | Graduated from a confirmed hypothesis | High (earned) |

**Traces.** Every reasoning chain is recorded as a hierarchical tree of spans,
each tagged with its epistemological kind: `ENTAILMENT`, `PERCEPTION`,
`LLM_CALL`, `TOOL_CALL`, `REASONING`. You can follow the chain from the moment
the TBox was injected, through which signals were active, to which the agent
referenced, to how the recommendation followed. If you claim the system's
perception is shaped by institutional expertise, the trace *proves* it at the
span level. Without the trace layer, that claim is unverifiable — and
unverifiable claims about intelligence are worthless.

---

## III. Three Modes of Reasoning

### The Peircean Architecture

Charles Sanders Peirce identified three irreducible modes of inference:
deduction, induction, and abduction. Most AI systems collapse all three into one
black box. We separate them architecturally, because they have fundamentally
different properties — different certainties, different outputs, different
authorities — and conflating them is how systems become unaccountable.

**Deduction: Known Law + Observed Fact → Predicted State.**
The entailment engine takes a signal definition from the TBox (a "law" of the
domain — e.g., "DelinquencyConcentration fires when delinquency_rate exceeds
8%"), queries the PropertyStore for the current state (the "fact" — this
manager's delinquency rate is 12%), and produces a Signal. The output is
*certain given the rules and data*. If the rules are right and the data is
right, the signal is right. No ambiguity. Full evidence chain. This is the
physics textbook applied.

**Induction: Observed Patterns → Candidate Law.**
The pattern detector scans the data through the OntologyStore — agnostically,
across any object type — looking for statistical outliers, correlations, and
concentration patterns. When it finds something (e.g., "days_vacant has outliers
at 4.2 standard deviations — should we formalize a threshold?"), it produces a
**Hypothesis**, not a Signal. A Hypothesis is explicitly provisional. It carries
a confidence score, a sample size, and a proposed TBox entry. It must be
reviewed by a human and confirmed before it becomes part of the domain's known
physics. Until then, it has no authority. This is the scientific method:
observation, hypothesis, confirmation, law.

**Abduction: Observed Signals → Best Explanation.**
The LLM receives the active signals, their evidence, and the user's question.
It reads unstructured text the rule engine cannot parse. It connects signals the
rules cannot connect — a maintenance backlog and a vacancy duration signal on
the same portfolio are probably related, but that causal link isn't in the TBox
yet. It recommends actions. It translates machine state into human language.
This is the scientist interpreting results. Powerful, necessary, and *explicitly
bounded*: the LLM never recomputes what the entailment engine already knows.

The boundaries between these modes are enforced by the architecture, not by
convention. The entailment engine produces `Signal` objects. The pattern detector
produces `Hypothesis` objects. The LLM produces natural language tagged
`INFERRED`. Each mode has a type, a trust level, and a lane.

### Why the Boundaries Matter

When deduction and abduction are collapsed — when you let the LLM both detect
problems and explain them — you get a system that sounds authoritative about
everything and is accountable for nothing. The model might say "there's a lease
cliff" because it pattern-matched on the word "expiring" in a maintenance note.
Or it might miss a real lease cliff because the data was in a format it didn't
attend to. You would never know, because the reasoning is opaque.

When induction is allowed to produce live signals without confirmation — when
data patterns automatically become system beliefs — you get a system that
mistakes correlation for causation and noise for signal, with no human
checkpoint.

The three modes must be separate because their epistemic properties are
separate. Deduction is certain (given premises). Induction is probabilistic
(requires confirmation). Abduction is plausible (requires verification). A
system that treats them all the same is a system that has no theory of its own
reliability.

---

## IV. The Architecture of Knowing

### Two Irreducible Kinds of Knowledge

The foundational distinction, borrowed from Description Logic, is between the
**TBox** (terminological box) and the **ABox** (assertion box).

The **TBox** defines what kinds of things exist and what they mean. It contains
concept definitions, inference rules, thresholds, policies, and causal chains.
It is not data. It is *institutional expertise, formalized*. In our system, it
is a single YAML file that a domain expert can read, correct, and extend without
touching code. It answers questions like: *What is a ChronicVacancy? What counts
as a LeaseExpirationCliff? What does it mean for a manager to be
underperforming?*

The **ABox** contains individual facts asserted about the world. Properties,
units, leases, tenants, maintenance requests. What actually happened. No
interpretation.

These two kinds of knowledge have different trust profiles, different authors,
different lifecycles, and different rates of change. The TBox changes when the
institution learns something new about its domain. The ABox changes every time a
report is uploaded. Collapsing them into one representation — as most AI systems
do, by embedding everything into a vector store or a prompt — is how systems
lose the ability to explain themselves.

Without a TBox, the system has data but no meaning. The LLM is forced to
reconstruct domain expertise from scratch on every query — slowly,
inconsistently, and without accumulation. Without an ABox, the TBox has rules
but nothing to apply them to. The **entailment engine** combines them: it
evaluates TBox rules against ABox facts and produces **Signals** — named,
evidenced, severity-ranked states that represent what is currently true about
the world.

### Signals: The System's Claims About Reality

A Signal is the system's formal claim that a specific state obtains. It is not
raw data (that's the ABox). It is not a rule (that's the TBox). It is the
*output of applying a rule to data* — a synthetic judgment, in Kant's
terminology.

Every Signal carries:

- A **name** drawn from the TBox vocabulary (e.g., DelinquencyConcentration)
- A **severity** (low, medium, high, critical)
- An **entity** it applies to (a specific manager, property, or unit)
- **Evidence** — the structured data that triggered the signal
- **Provenance** — how the signal was produced

Signals are the bridge between the system's internal state and the human's
decision-making. The director doesn't need to query raw data. She looks at
signals. If there are no signals, the portfolio is within normal parameters.
If there are signals, each one is named, explained, and grounded in evidence
she can inspect.

### The Hypothesis Pipeline: How the System Learns

Knowledge in the system is not static. It grows through a disciplined process
that mirrors the scientific method:

1. The **PatternDetector** scans ABox data through the OntologyStore, looking
   for statistical regularities — outlier distributions, correlations between
   fields, concentration patterns.

2. When it finds something, it produces a **Hypothesis** — a candidate TBox
   entry with a confidence score, sample size, and proposed formalization (a
   new signal definition, a new causal chain, a threshold adjustment).

3. A human reviews the hypothesis: **CONFIRMED**, **REJECTED**, or **EXPIRED**
   (never reviewed in time).

4. Confirmed hypotheses are **graduated** into the live TBox. They become real
   rules the entailment engine uses going forward. They carry the provenance
   tag `LEARNED` — they are real now, but they remember their origins.

This is not machine learning in the conventional sense. There are no weight
updates, no fine-tuning, no opaque model changes. Knowledge enters the system
through typed, provenance-tagged, human-reviewable channels. The system learns
*through structure*, not through parameters.

### Perception as Construction

When the agent begins a conversation, before it processes the user's question,
the system performs two acts of perceptual construction:

**TBox injection.** The domain ontology — signal definitions, thresholds,
policies, causal chains — is rendered into a structured context block and
inserted into the agent's message thread. This is not background information.
This is the agent's *categorical apparatus*: the vocabulary through which it
will perceive everything that follows.

**Signal injection.** The currently active signals — pre-computed by the
entailment engine — are rendered and inserted. The agent sees what the system
already knows is true before it begins its own reasoning.

This is top-down processing, as understood in cognitive neuroscience. Biological
perception is not bottom-up: the brain does not passively receive sensory data
and then interpret it. The brain's existing models shape what is perceived in the
first place. Expectations structure sensation. Our architecture implements this
deliberately. The agent's world model is constituted by the institution's
expectations before a single token of user input is processed.

### The Trace as Proof

Every step in the system's reasoning — from entailment through perception
through tool use through the agent's final output — is recorded as a
hierarchical trace with epistemologically typed spans:

| Span Kind | What It Captures |
|-----------|-----------------|
| `ENTAILMENT` | A TBox rule evaluated against ABox facts |
| `PERCEPTION` | The agent receiving its world model |
| `LLM_CALL` | A raw model request and response |
| `TOOL_CALL` | The agent invoking a tool |
| `REASONING` | The agent's synthesized output |
| `SIGNAL` | A signal produced or referenced |

The trace is not telemetry. It is the system's *proof* that institutional
expertise actually shaped what the AI perceived, considered, and recommended.
Without it, the claim that "domain knowledge drives the system" is marketing.
With it, you can follow the chain span by span and verify it yourself.

---

## V. What We Believe About Intelligence

### Intelligence Is Structured Perception

The dominant narrative in AI is that intelligence comes from scale — more
parameters, more data, more compute. We believe this is a category error. Raw
processing power, without structure, produces fluency without understanding. The
model that sounds most confident is not the model that knows the most. The model
that knows the most is the one that perceives through the right categories.

This is a Kantian claim applied to artificial systems: intelligence is not the
power of the processor but the quality of the categories the processor operates
within. A generic model, perceiving through the formalized expertise of an
institution, will produce better judgments than a more powerful model perceiving
through nothing.

### Expertise Is Institutional, Not Individual

Expertise locked in one person's head — or in one model's weights — is fragile,
opaque, and non-transferable. When the expert leaves the organization, the
expertise leaves with them. When the model is updated, the fine-tuned knowledge
may silently degrade.

We believe expertise should be *first-class*: typed, versioned, reviewable,
editable by domain experts without engineering intermediation. In our system,
the TBox is a YAML file. A director can read it and say "30 days is too
aggressive for chronic vacancy in this market — it should be 45." She changes
the number. The entailment engine uses the new threshold on the next run. No
code deploy. No retraining. No opacity.

The ontology is not a static schema. It is a **living epistemic artifact** —
the formalized, accumulated expertise of the institution, growing over time
through calibrated thresholds, observed causal chains, codified observations,
and graduated hypotheses.

### The Model Is a Reader, Not a Knower

We position the LLM precisely. It is extraordinarily good at reading
unstructured text, connecting disparate signals, forming hypotheses, and
translating machine state into human language. These capabilities are genuine
and valuable.

But the model is the *scientist interpreting results*. It is not the physics
textbook (the TBox). It is not the measurement instrument (the entailment
engine). It is not the experimental apparatus (the data pipeline). When we say
"the LLM never recomputes what the entailment engine already knows," we mean
that literally — and we mean it as a design principle, not a performance
optimization.

Abduction — inference to the best explanation — is the model's proper mode. It
reads signals, explains them, connects them, recommends actions. It does not
override the rule engine. It does not produce signals. Its outputs carry the
provenance tag `INFERRED`, not `DATA_DERIVED`. The system knows the difference
between what it has *computed* and what it has *guessed*, and it tells the user.

### The Right Response to Uncertainty Is Discipline, Not Confidence

Most AI systems are designed to maximize the appearance of certainty. We are
designed to maximize the *transparency of uncertainty*. When the system is
certain (a signal produced by the entailment engine from verified rules and
data), it says so with full evidence. When the system is uncertain (an LLM
inference, a statistical pattern, an unconfirmed hypothesis), it says *that* —
with the provenance, confidence score, and sample size that let the human make
their own judgment.

Hypotheses are not signals. Statistical patterns require human confirmation
before they become laws. Inferred observations are tagged as inferred. We do not
move fast and guess confidently. We move carefully and say what we actually know,
how we know it, and how much we trust it.

### Verifiability Is Non-Negotiable

A system that claims to be knowledge-driven must be able to prove it. Not
through marketing copy. Through a trace you can follow, span by span, from the
injection of the TBox through the production of signals through the agent's
perception through its reasoning to its output. If you cannot show that
institutional expertise *actually shaped* the system's behavior in a specific
interaction, you should not claim that it did.

The trace layer is not optional infrastructure. It is the epistemological
foundation of the system's credibility.

---

## VI. The Grammar of Epistemic Acts

Our command-line interface is not a developer tool. It is a formal language for
epistemic acts — the grammar through which any participant (human or AI) engages
with institutional knowledge:

| Command | Epistemic Act |
|---------|--------------|
| `onto signals` | Query: What is currently entailed to be true? |
| `onto explain` | Justify: What evidence supports this claim? |
| `onto infer` | Derive: Re-evaluate all rules against current facts |
| `onto codify` | Assert: Enter a new piece of knowledge into the system |
| `onto schema` | Inspect: What categories of knowledge exist? |

This grammar is **stable across domains**. Only the TBox content changes. A
system deployed in healthcare would use the same commands with different signal
definitions, different thresholds, different policies. The epistemological
structure — observe, assert, derive, explain, act — is universal wherever
institutional expertise shapes decisions.

An agent — human or artificial — that has learned this grammar can operate in
any domain the framework supports. It does not need to learn new commands. It
needs a new TBox. The domain is the variable. The structure of knowing is the
constant.

---

## VII. From Philosophy to Practice: The Incline Framework

### The Domain-Agnostic Core

Everything described above — the ontology system, entailment engine, signal
framework, hypothesis pipeline, trace layer, vector retrieval, agent loop, and
tool system — is domain-agnostic. We call this layer **Incline**. It is the
reusable intellectual property: a framework for building domain-intelligent AI
products.

A product built on Incline provides six things:

1. **A TBox** — signal definitions, thresholds, policies, causal chains,
   expressed in YAML
2. **A domain store** — the ABox adapter for the product's entities
3. **Agent workflows** — YAML-declared agents with domain-specific prompts and
   tool sets
4. **Core type bindings** — mapping domain entities to the unified ontology
   interface
5. **Evaluators** — signal evaluation logic for domain-specific rule conditions
6. **Domain interfaces** — API routes and CLI commands for domain-specific
   queries

Everything else — the runtime, the reasoning engine, the learning pipeline, the
trace layer, the sandbox, the LLM loop — is Incline.

The litmus test: *Would this exist if we replaced the current domain with
healthcare, logistics, or finance?* If yes, it belongs to the framework. If no,
it belongs to the product.

### REMI: The First Proof

REMI — Real Estate Management Intelligence — is the first product built on
Incline. It serves directors of property management companies, people who
oversee multiple managers, each running portfolios of 15–40 properties. The
director's core question, every day, is: *Which of my managers needs my
attention, and why?*

REMI's TBox defines twelve signals across three categories — portfolio health,
manager performance, and operational compliance — with calibrated thresholds,
five deontic policies, and four known causal chains. Its ABox contains
structured data for properties, units, leases, tenants, and maintenance
requests, ingested from property management systems like AppFolio.

The entailment engine evaluates TBox rules against this data and produces
signals. The LLM agent — a single unified director agent with mode-switching
from quick answers through investigation to deep sandbox-based research —
explains, connects, and recommends based on those signals.

REMI is deliberately narrow. It proves the architecture in one vertical. The
architecture itself is designed to carry any vertical where institutional
expertise shapes decisions — which is to say, nearly all of them.

---

## VIII. The Argument, Summarized

1. **Intelligence is not a property of models. It is a property of the
   structures models operate within.** A model without domain categories will
   improvise expertise on every query. A model with the right categories — the
   right TBox — will perceive correctly.

2. **Knowledge has two irreducible components: what things mean (TBox) and what
   has happened (ABox).** These must be represented separately, authored by
   different people, versioned independently, and combined by a formal engine
   that produces auditable outputs.

3. **There are three modes of reasoning, and they must not be confused.**
   Deduction (certain, rule-based), induction (probabilistic, requires
   confirmation), and abduction (plausible, requires verification) have
   different properties and different authorities. Collapsing them produces
   systems that cannot account for their own reliability.

4. **The justification chain matters as much as the conclusion.** A correct
   answer reached for the wrong reasons is not knowledge. Provenance and traces
   exist to ensure that every claim can be followed back to its epistemological
   origin.

5. **Expertise is institutional property that should outlive any individual.**
   The TBox is a living artifact — typed, reviewable, editable by domain
   experts, accumulating through a disciplined process of observation,
   hypothesis, confirmation, and formalization.

6. **The LLM is powerful and bounded.** It reads, explains, connects, and
   translates. It does not detect, decide, or override. Its outputs are tagged
   with their epistemic status and presented accordingly.

7. **A system that claims to know things must be able to prove how it knows
   them.** The trace layer is not optional. It is the foundation of trust.

8. **This architecture is domain-agnostic.** The epistemological structure —
   TBox/ABox, entailment, hypotheses, provenance, traces — applies wherever
   institutional expertise shapes decisions. The content changes. The structure
   of knowing does not.

---

*The software described in this paper is operational. The architecture is
running, the entailment engine evaluates rules, the hypothesis pipeline proposes
and graduates candidate laws, the trace layer records every reasoning step, and
the agent perceives through the institution's categories. This is not a
proposal. It is a proof of concept in production — and a statement of conviction
about how AI systems should relate to knowledge.*
