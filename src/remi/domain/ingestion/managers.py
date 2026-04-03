"""Manager resolution for the ingestion pipeline.

Extracts manager tags from report rows using a declared extraction
strategy, classifies them via frequency analysis (real managers manage
portfolios of properties; tags appear on few), and resolves/upserts
PropertyManager + Portfolio records.
"""

from __future__ import annotations

from enum import StrEnum

import structlog

from remi.domain.portfolio.models import (
    Portfolio,
    PropertyManager,
)
from remi.domain.portfolio.protocols import (
    ManagerRepository,
    PortfolioRepository,
)
from remi.domain.portfolio.rules import manager_name_from_tag
from remi.types.text import slugify

logger = structlog.get_logger(__name__)

_MIN_PROPERTIES_FOR_MANAGER = 3


class ManagerExtraction(StrEnum):
    """How to extract the manager tag from a row's raw field value."""

    NONE = "none"
    DIRECT = "direct"
    COMMA_SPLIT_FIRST = "comma_split_first"


def extract_manager_tag(raw: str | None, strategy: ManagerExtraction) -> str | None:
    """Apply extraction strategy to a raw field value, returning a tag or None."""
    if not raw or strategy == ManagerExtraction.NONE:
        return None
    raw = raw.strip()
    if not raw:
        return None

    if strategy == ManagerExtraction.DIRECT:
        return raw

    if strategy == ManagerExtraction.COMMA_SPLIT_FIRST:
        segment = raw.split(",")[0].strip()
        if segment and segment.lower() != "month-to-month":
            return segment
        return None

    return raw


def classify_manager_values(
    property_tags: dict[str, str],
) -> set[str]:
    """Return tag values that represent real managers based on frequency.

    ``property_tags`` maps property_id → manager tag (one tag per property,
    first non-empty value wins). Real managers manage portfolios: they appear
    across many *distinct properties*. Tags/labels appear on few.

    Tags are normalized (whitespace-collapsed) before counting so that
    "Aaron  Smay" and "Aaron Smay" count as the same value.
    """
    if not property_tags:
        return set()

    normalized_to_properties: dict[str, set[str]] = {}
    raw_to_normalized: dict[str, str] = {}
    for prop_id, tag in property_tags.items():
        normalized = manager_name_from_tag(tag)
        raw_to_normalized[tag] = normalized
        normalized_to_properties.setdefault(normalized, set()).add(prop_id)

    counts = {n: len(ps) for n, ps in normalized_to_properties.items()}
    manager_names = {n for n, c in counts.items() if c >= _MIN_PROPERTIES_FOR_MANAGER}
    skipped = {n: c for n, c in counts.items() if c < _MIN_PROPERTIES_FOR_MANAGER}

    if manager_names or skipped:
        logger.info(
            "manager_value_classification",
            managers={n: counts[n] for n in sorted(manager_names)},
            tags_skipped=dict(sorted(skipped.items())),
        )

    return {tag for tag, n in raw_to_normalized.items() if n in manager_names}


class ManagerResolver:
    """Resolves manager tags to portfolio IDs, creating managers as needed."""

    def __init__(
        self,
        manager_repo: ManagerRepository,
        portfolio_repo: PortfolioRepository,
    ) -> None:
        self._managers = manager_repo
        self._portfolios = portfolio_repo

    async def ensure_manager(self, manager_tag: str) -> str:
        """Create or retrieve a manager + portfolio. Returns portfolio_id.

        When the resolved name doesn't match an existing manager exactly,
        we check for a first-name match and merge into that record rather
        than creating a duplicate. The longer name wins.
        """
        mgr_name = manager_name_from_tag(manager_tag)
        manager_id = slugify(f"manager:{mgr_name}")

        existing = await self._managers.get_manager(manager_id)
        if existing:
            await self._managers.upsert_manager(
                PropertyManager(id=manager_id, name=mgr_name, manager_tag=manager_tag)
            )
        else:
            resolved_id, resolved_name = await self._resolve_alias(mgr_name)
            if resolved_id:
                manager_id = resolved_id
                mgr_name = resolved_name  # type: ignore[assignment]
            else:
                await self._managers.upsert_manager(
                    PropertyManager(id=manager_id, name=mgr_name, manager_tag=manager_tag)
                )

        portfolio_id = slugify(f"portfolio:{mgr_name}")
        await self._portfolios.upsert_portfolio(
            Portfolio(
                id=portfolio_id,
                manager_id=manager_id,
                name=f"{mgr_name} Portfolio",
            )
        )
        return portfolio_id

    async def _resolve_alias(self, name: str) -> tuple[str | None, str | None]:
        """Find an existing manager that matches the given name.

        Two-tier matching:
          1. Normalized slug match — handles casing/whitespace variants.
          2. First-name + prefix match — handles partial names like "Denise"
             upgrading to "Denise Shoemaker".

        The longer name always wins so records become more complete over time.
        """
        if not name:
            return None, None

        target_slug = slugify(f"manager:{name}")
        managers = await self._managers.list_managers()

        for m in managers:
            if m.id == target_slug:
                canonical = name if len(name) > len(m.name) else m.name
                if len(canonical) > len(m.name):
                    await self._managers.upsert_manager(
                        PropertyManager(id=m.id, name=canonical, manager_tag=m.manager_tag)
                    )
                return m.id, canonical

        first_name = name.split()[0].lower()
        for m in managers:
            m_first = m.name.split()[0].lower() if m.name else ""
            if m_first != first_name:
                continue
            if m.name.lower().startswith(name.lower()) or name.lower().startswith(
                m.name.lower()
            ):
                canonical = name if len(name) > len(m.name) else m.name
                if len(canonical) > len(m.name):
                    await self._managers.upsert_manager(
                        PropertyManager(id=m.id, name=canonical, manager_tag=m.manager_tag)
                    )
                return m.id, canonical

        return None, None
