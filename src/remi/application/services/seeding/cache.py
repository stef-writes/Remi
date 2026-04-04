"""Dev seed cache — snapshot and restore in-memory store state.

Saves the fully populated state of all in-memory stores to a single JSON
file after the first successful seed run.  Subsequent seeds detect the
cache and hydrate stores directly, skipping the LLM pipeline entirely.

The cache auto-invalidates when any source report file is newer than the
cache file itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from remi.agent.documents.mem import InMemoryDocumentStore
from remi.agent.graph.adapters.mem import InMemoryKnowledgeStore
from remi.agent.signals.persistence.mem import InMemoryFeedbackStore, InMemorySignalStore
from remi.application.infra.stores.mem import InMemoryPropertyStore
from remi.application.infra.stores.rollups import InMemoryRollupStore

logger = structlog.get_logger(__name__)

_CACHE_VERSION = 1


@dataclass
class StoreBundle:
    """References to the in-memory stores that should be snapshot/restored."""

    property_store: InMemoryPropertyStore
    knowledge_store: InMemoryKnowledgeStore
    document_store: InMemoryDocumentStore
    signal_store: InMemorySignalStore
    feedback_store: InMemoryFeedbackStore
    rollup_store: InMemoryRollupStore


def cache_path_for(report_dir: Path) -> Path:
    """Derive the cache file path from the report directory."""
    return report_dir / ".dev-seed-cache.json"


def is_stale(cache_file: Path, report_dir: Path) -> bool:
    """Return True if cache doesn't exist or is older than any source file."""
    if not cache_file.exists():
        return True

    cache_mtime = cache_file.stat().st_mtime
    for p in report_dir.iterdir():
        is_report = p.is_file() and p.suffix.lower() in {".xlsx", ".xls", ".csv"}
        if is_report and p.stat().st_mtime > cache_mtime:
            logger.info(
                "seed_cache_stale",
                reason="source_file_newer",
                file=p.name,
            )
            return True
    return False


def save(stores: StoreBundle, cache_file: Path) -> None:
    """Dump all store state to a JSON file."""
    payload: dict[str, Any] = {
        "_version": _CACHE_VERSION,
        "property_store": stores.property_store.dump_state(),
        "knowledge_store": stores.knowledge_store.dump_state(),
        "document_store": stores.document_store.dump_state(),
        "signal_store": stores.signal_store.dump_state(),
        "feedback_store": stores.feedback_store.dump_state(),
        "rollup_store": stores.rollup_store.dump_state(),
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, default=str, indent=None))
    logger.info(
        "seed_cache_saved",
        path=str(cache_file),
        size_mb=round(cache_file.stat().st_size / 1_048_576, 2),
    )


def load(stores: StoreBundle, cache_file: Path) -> bool:
    """Restore store state from a cached JSON file. Returns True on success."""
    try:
        raw = json.loads(cache_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("seed_cache_read_failed", error=str(exc), exc_info=True)
        return False

    if raw.get("_version") != _CACHE_VERSION:
        logger.info(
            "seed_cache_version_mismatch",
            expected=_CACHE_VERSION,
            got=raw.get("_version"),
        )
        return False

    stores.property_store.load_state(raw.get("property_store", {}))
    stores.knowledge_store.load_state(raw.get("knowledge_store", {}))
    stores.document_store.load_state(raw.get("document_store", []))
    stores.signal_store.load_state(raw.get("signal_store", []))
    stores.feedback_store.load_state(raw.get("feedback_store", []))
    stores.rollup_store.load_state(raw.get("rollup_store", {}))

    logger.info("seed_cache_loaded", path=str(cache_file))
    return True
