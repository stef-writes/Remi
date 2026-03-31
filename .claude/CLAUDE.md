# REMI

AI platform for property management directors. The director's core question: **which of my managers needs my attention, and why?**

## Commands

```bash
uv run pytest tests/ -q              # run all tests
uv run pytest tests/domain/ -q       # run a specific folder
uv run remi serve                    # start API server
uv run remi onto signals             # show active signals
uv run remi trace list               # recent traces
```

## Tooling Rules

- Always use `uv run` to execute Python — never `python` directly
- Always use `uv add` to add dependencies — never `pip install`
- Never reference `.venv/` paths directly

## Error Handling

- Never silently swallow errors — let them raise
- No bare `except`, no `except Exception: pass`, no returning `None` to mask failures
- Use `structlog` for logging, not `print` or `logging` directly

## Tests

- Only write tests for meaningful behavior — not implementation details or happy-path tautologies
- Tests should cover real failure modes and edge cases worth caring about
- Ask before writing tests if the value isn't obvious

## Architecture: Four Layers

```
Layer 1 — Facts       stores/          PropertyStore, KnowledgeStore, DocumentStore
Layer 2 — Domain      config/          domain.yaml (rulebook), ontology (schema)
Layer 3 — Signals     services/        entailment engine → SignalStore; pattern detector → HypothesisStore
Layer 4 — Interface   api/, cli/       FastAPI routes, Typer CLI, agent loop
```

**When creating or moving code, say which layer it belongs to before placing it.**

Key constraint: the LLM agent does NOT detect signals — the entailment engine does.  
The LLM's job is abductive reasoning: explain, connect, recommend, codify.

## Key Files

| File | Role |
|------|------|
| `src/remi/config/domain.yaml` | Source of truth for signal definitions, thresholds, rules, policies |
| `src/remi/agents/director/app.yaml` | Director agent — system prompt, tools, modes |
| `src/remi/agent/node.py` | AgentNode — config-driven think-act-observe loop |
| `src/remi/knowledge/context_builder.py` | Assembles agent context from knowledge graph + signals |
| `src/remi/knowledge/graph_retriever.py` | Retrieves entities and relationships from the graph |
| `src/remi/services/dashboard.py` | Computes director dashboard state from signals |
| `src/remi/shared/errors.py` | Shared error types — use these, don't invent new ones |

## Module Map

```
src/remi/
  agent/        AgentNode, loop, intent classifier, LLM bridge, tool executor
  agents/       App YAML configs (director, knowledge_enricher, report_classifier)
  api/          FastAPI routers (realtime chat, agents, documents)
  cli/          Typer CLI entry points
  config/       Settings, DI container, domain.yaml
  knowledge/    Context builder, graph retriever
  llm/          LLM provider ports + adapters (Anthropic, OpenAI, Gemini)
  models/       Pydantic models (properties, signals, trace, memory, documents)
  services/     Domain services (dashboard, manager review, lease queries, etc.)
  stores/       Storage adapters (properties, signals, vectors, chat, trace, memory)
  tools/        Agent tool implementations (onto_*, sandbox_*, trace_*, memory_*)
  shared/       Enums, errors, ids, clock, result types — cross-cutting primitives
```

## When Making Structural Decisions

- Before creating a new file, say where it goes and why
- Before adding logic to an existing file, flag if it's growing beyond a single responsibility
- Prefer small focused modules — don't accumulate logic in existing files
- `shared/` is for primitives only — no business logic there
- `services/` is for domain logic that isn't part of the agent loop
