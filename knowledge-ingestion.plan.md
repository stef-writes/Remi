---
name: Knowledge Ingestion and Knowledge Base
overview: |
  Connect uploaded documents to agents through a knowledge graph. On upload, documents are auto-ingested via rule-based entity extraction (with optional LLM enrichment). New agent tools let REMI agents query both raw document rows and the entity/relationship graph.
todos:
  - id: ingestion-service
    content: "Create IngestionService — rule-based entity extractor that maps document columns to domain entities (property, tenant, lease, unit, etc.) and relationships, writing to KnowledgeStore"
    status: done
  - id: enrichment-agent
    content: "Create LLM enrichment agent YAML + module that takes ambiguous rows and emits structured entities (optional pass, skipped when no API key)"
    status: done
  - id: upload-hook
    content: "Wire ingestion into document upload — after DocumentStore.save(), run IngestionService.ingest(doc) automatically"
    status: done
  - id: doc-tools
    content: "Add document_query and document_list CLI commands + CLI-bridged tools via cli_tools.py"
    status: done
  - id: kb-tools
    content: "Add kb_search, kb_related, and kb_summary CLI commands + CLI-bridged tools via cli_tools.py"
    status: done
  - id: wire-stores
    content: "Pass knowledge_store and document_store into context_extras (tools are CLI-bridged, not in-process)"
    status: done
  - id: update-agents
    content: "Agent YAMLs updated to use ontology tools (onto_*) which subsume KB tools; document tools retained"
    status: done
  - id: tests
    content: "Tests for IngestionService, cli_tools registration, upload-to-knowledge-graph flow"
    status: done
isProject: false
---

# Knowledge Ingestion and Knowledge Base

## Status: COMPLETE

All items implemented. Architecture note: tools follow the CLI-as-Tool pattern
(`cli_tools.py` with `CliToolSpec`), not the old in-process `remi_tools.py`
pattern referenced in the original plan text below. Agent YAMLs now use
`onto_*` ontology tools which subsume the `kb_*` tools.

## Original Plan (for reference)

## Part 1: IngestionService — Rule-Based Entity Extraction

New file: `src/remi/infrastructure/knowledge/ingestion.py`

Maps document columns to domain entity types using heuristic rules:
- Columns containing "property", "building", "address" → `property` entity
- Columns containing "tenant", "resident", "occupant" → `tenant` entity
- Columns containing "unit", "apt", "suite" → `unit` entity
- Columns containing "lease", "contract" → `lease` entity
- Columns containing "rent", "revenue", "income", "expense" → `financial` entity
- Columns containing "maintenance", "repair", "work order" → `maintenance` entity

For each row, the service:
1. Creates `Entity` objects (entity_type from column mapping, properties from row values)
2. Infers `Relationship`s between co-occurring entities in the same row (e.g., tenant → occupies → unit)
3. Writes entities and relationships to `KnowledgeStore` under a namespace tied to the document ID

Also stores document-level metadata as a `document` entity so agents can discover what's been ingested.

Ambiguous rows (no column matches, or mixed/unclear data) are collected and returned from `ingest()` for optional LLM enrichment.

## Part 2: LLM Enrichment Agent (Optional)

New file: `src/remi/apps/knowledge_enricher/app.yaml`

A lightweight agent that receives ambiguous rows and returns structured entity/relationship JSON. The enrichment pass:
- Is skipped when no LLM API key is configured (graceful degradation)
- Runs after rule-based extraction, only on rows that couldn't be classified
- Uses a strict JSON output format so results can be parsed and fed into `KnowledgeStore`

New file: `src/remi/infrastructure/knowledge/enrichment.py` — orchestrates calling the enrichment agent and writing results to the KnowledgeStore.

## Part 3: Wire Ingestion into Upload

Modify [src/remi/interfaces/api/routers/documents.py](src/remi/interfaces/api/routers/documents.py):
- After `await store.save(doc)`, call `await ingestion_service.ingest(doc)`
- `ingestion_service` is obtained from the Container
- Response includes `entities_extracted` count alongside existing fields

Modify [src/remi/infrastructure/config/container.py](src/remi/infrastructure/config/container.py):
- Create `IngestionService` instance wired to `knowledge_store`
- Expose as `container.ingestion_service`

## Part 4: Document Tools for Agents

Add to [src/remi/infrastructure/tools/remi_tools.py](src/remi/infrastructure/tools/remi_tools.py):

**`document_query`** — search uploaded document rows by column filters or text query
- Args: `document_id` (optional), `query` (text search across all docs), `filters` (column=value), `limit`
- Uses `DocumentStore.query_rows()` and `DocumentStore.list_documents()`

**`document_list`** — list all uploaded documents with metadata (filename, columns, row count, upload date)
- No required args
- Uses `DocumentStore.list_documents()`

## Part 5: Knowledge Graph Tools for Agents

Add to [src/remi/infrastructure/tools/remi_tools.py](src/remi/infrastructure/tools/remi_tools.py):

**`kb_search`** — find entities in the knowledge graph by type and/or text query
- Args: `entity_type` (optional: property, tenant, unit, lease, financial, maintenance), `query` (text search), `limit`
- Uses `KnowledgeStore.find_entities()`

**`kb_related`** — find entities related to a given entity (graph traversal)
- Args: `entity_id`, `relation_type` (optional), `direction` (outgoing/incoming/both), `max_depth`
- Uses `KnowledgeStore.get_relationships()` and `KnowledgeStore.traverse()`

**`kb_summary`** — high-level summary of the knowledge base (entity counts by type, relationship counts, recent ingestions)
- No required args
- Uses `KnowledgeStore.find_entities()` for each type

## Part 6: Wire Stores into Tools and Context

Modify [src/remi/infrastructure/tools/remi_tools.py](src/remi/infrastructure/tools/remi_tools.py):
- Add `knowledge_store: KnowledgeStore | None = None` and `document_store: DocumentStore | None = None` to `register_remi_tools()` signature

Modify [src/remi/infrastructure/config/container.py](src/remi/infrastructure/config/container.py):
- Pass `knowledge_store` and `document_store` to `register_remi_tools()`
- Add both to `context_extras` dict

Modify [src/remi/interfaces/api/routers/ws.py](src/remi/interfaces/api/routers/ws.py):
- Add `knowledge_store` and `document_store` to the chat agent's `RuntimeContext.extras`

## Part 7: Update Agent YAML Configs

Modify all three agent configs to include the new tools:

[src/remi/apps/portfolio_analyst/app.yaml](src/remi/apps/portfolio_analyst/app.yaml):
- Add: `document_query`, `document_list`, `kb_search`, `kb_related`, `kb_summary`
- Update system prompt to mention knowledge base capabilities

[src/remi/apps/property_inspector/app.yaml](src/remi/apps/property_inspector/app.yaml):
- Add: `document_query`, `kb_search`, `kb_related`

[src/remi/apps/maintenance_triage/app.yaml](src/remi/apps/maintenance_triage/app.yaml):
- Add: `document_query`, `kb_search`, `kb_related`

## Part 8: Tests

New test files:

`tests/unit/infrastructure/test_ingestion.py`:
- Test rule-based column mapping for each entity type
- Test relationship inference between co-occurring entities
- Test that ambiguous rows are returned for enrichment
- Test ingestion of a full CSV document end-to-end

`tests/unit/infrastructure/test_knowledge_tools.py`:
- Test `kb_search`, `kb_related`, `kb_summary` tools with pre-populated KnowledgeStore
- Test `document_query`, `document_list` tools with pre-populated DocumentStore

`tests/unit/infrastructure/test_upload_ingestion.py`:
- Test that uploading a CSV triggers ingestion and populates the knowledge graph
- Test entity count in response
