"""Ingestion — document and data ingestion pipeline.

Two-tier pipeline: rule-based deterministic extraction first,
LLM fallback for unknown formats. The YAML workflow + tool registration
(application/tools/ingestion.py) own all entity work.

Files:
    models.py         All types: LLM output schemas, pipeline results, API responses
    pipeline.py       Thin host: parse → dedup → YAML workflow → save
    rules.py          Deterministic domain knowledge (junk filtering, coercion, address parsing)
    api.py            Document upload/query REST routes
    app.yaml          Agent manifest for document_ingestion agent
"""

from pathlib import Path

from .pipeline import DocumentIngestService

MANIFEST_PATH = Path(__file__).parent / "app.yaml"

__all__ = [
    "DocumentIngestService",
    "MANIFEST_PATH",
]
