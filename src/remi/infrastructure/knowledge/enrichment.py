"""LLM enrichment pass for ambiguous document rows.

Sends unclassified rows to the knowledge-enricher agent and writes
the resulting entities/relationships to the KnowledgeStore.
Gracefully degrades when no LLM API key is available.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from remi.domain.documents.models import Document
from remi.domain.memory.ports import Entity, KnowledgeStore, Relationship

if TYPE_CHECKING:
    from remi.infrastructure.config.container import InclineContainer

logger = structlog.get_logger(__name__)


def _llm_available(container: InclineContainer) -> bool:
    """Check if any LLM API key is configured via settings."""
    s = container.settings.secrets
    return bool(s.openai_api_key or s.anthropic_api_key or s.google_api_key)


async def enrich_ambiguous_rows(
    rows: list[dict[str, Any]],
    doc: Document,
    knowledge_store: KnowledgeStore,
    container: InclineContainer,
) -> tuple[int, int]:
    """Run LLM enrichment on ambiguous rows. Returns (entities_created, relationships_created).

    Skipped silently when no LLM API key is configured.
    """
    if not rows:
        return 0, 0

    if not _llm_available(container):
        logger.info(
            "enrichment_skipped_no_api_key",
            doc_id=doc.id,
            ambiguous_rows=len(rows),
        )
        return 0, 0

    namespace = f"doc:{doc.id}"

    try:
        from remi.infrastructure.loaders.yaml_loader import YamlAppLoader
        from remi.shared.ids import AppId, ModuleId
        from remi.shared.paths import WORKFLOWS_DIR

        app_path = WORKFLOWS_DIR / "knowledge_enricher" / "app.yaml"
        if not app_path.exists():
            logger.warning("enrichment_app_not_found", path=str(app_path))
            return 0, 0

        loader = YamlAppLoader()
        app_def = loader.load(str(app_path))

        reg_result = container.register_app_uc.execute(app_def)
        if reg_result.is_err:
            logger.warning("enrichment_app_registration_failed", errors=reg_result.unwrap_err())
            return 0, 0

        batch_size = 20
        total_entities = 0
        total_rels = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            payload = json.dumps(
                [{"row_index": i + j, **row} for j, row in enumerate(batch)],
                default=str,
            )

            result = await container.run_app_uc.execute(
                AppId(app_def.app_id),
                run_params={"input": payload},
            )

            agent_module_ids = [m.id for m in app_def.modules if m.kind == "agent"]
            output_mid = agent_module_ids[-1] if agent_module_ids else app_def.modules[-1].id
            state = await container.state_query.get_module_state(
                AppId(app_def.app_id), result.run_id, ModuleId(output_mid)
            )

            if state and state.output:
                e, r = await _parse_and_store(state.output, namespace, knowledge_store)
                total_entities += e
                total_rels += r

        logger.info(
            "enrichment_complete",
            doc_id=doc.id,
            entities=total_entities,
            relationships=total_rels,
        )
        return total_entities, total_rels

    except Exception as exc:
        logger.error("enrichment_failed", doc_id=doc.id, error=str(exc))
        return 0, 0


async def _parse_and_store(
    output: Any,
    namespace: str,
    kb: KnowledgeStore,
) -> tuple[int, int]:
    """Parse the enricher agent's JSON output and write to the KnowledgeStore."""
    entities_count = 0
    rels_count = 0

    if isinstance(output, str):
        try:
            output = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return 0, 0

    if not isinstance(output, dict):
        return 0, 0

    for row_data in output.get("rows", []):
        for ent in row_data.get("entities", []):
            etype = ent.get("entity_type", "unknown")
            eid = ent.get("entity_id", "")
            if not eid:
                continue
            await kb.put_entity(Entity(
                entity_id=eid,
                entity_type=etype,
                namespace=namespace,
                properties=ent.get("properties", {}),
                metadata={"source": "llm_enrichment", "row_index": row_data.get("row_index")},
            ))
            entities_count += 1

        for rel in row_data.get("relationships", []):
            src = rel.get("source_id", "")
            tgt = rel.get("target_id", "")
            rtype = rel.get("relation_type", "")
            if src and tgt and rtype:
                await kb.put_relationship(Relationship(
                    source_id=src,
                    target_id=tgt,
                    relation_type=rtype,
                    namespace=namespace,
                ))
                rels_count += 1

    return entities_count, rels_count
