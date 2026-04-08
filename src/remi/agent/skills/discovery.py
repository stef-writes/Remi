"""Skill discovery — find and load skill playbooks from the filesystem.

``SkillDiscovery`` is a protocol so the filesystem implementation can
be swapped for a registry-backed one later without changing consumers.

``FilesystemSkillDiscovery`` scans configured directories for SKILL.md
files, validates YAML frontmatter, and provides lazy loading of full
skill content.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any

import structlog
import yaml

from remi.agent.skills.types import SkillContent, SkillMetadata

logger = structlog.get_logger(__name__)

_FRONTMATTER_DELIMITER = "---"


def _parse_skill_file(path: Path) -> tuple[SkillMetadata, str] | None:
    """Parse a SKILL.md file into metadata + body.

    Returns None if the file is malformed or missing required fields.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("skill_read_error", path=str(path), exc_info=True)
        return None

    lines = raw.split("\n")
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        logger.warning("skill_missing_frontmatter", path=str(path))
        return None

    end_idx: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONTMATTER_DELIMITER:
            end_idx = i
            break

    if end_idx is None:
        logger.warning("skill_unterminated_frontmatter", path=str(path))
        return None

    frontmatter_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :]).strip()

    try:
        fm: dict[str, Any] = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        logger.warning("skill_invalid_yaml", path=str(path), exc_info=True)
        return None

    if "name" not in fm:
        logger.warning("skill_missing_name", path=str(path))
        return None

    try:
        metadata = SkillMetadata(**fm)
    except Exception:
        logger.warning("skill_validation_error", path=str(path), exc_info=True)
        return None

    return metadata, body


class SkillDiscovery(abc.ABC):
    """Protocol for discovering and loading agent skills."""

    @abc.abstractmethod
    def discover(self) -> list[SkillMetadata]:
        """Return metadata for all available skills."""

    @abc.abstractmethod
    def load(self, name: str) -> SkillContent | None:
        """Load full content for a skill by name."""


class FilesystemSkillDiscovery(SkillDiscovery):
    """Discovers skills from SKILL.md files in configured directories.

    Each skill lives in its own directory::

        .remi/skills/
            manager-review/SKILL.md
            portfolio-health/SKILL.md
    """

    def __init__(self, search_paths: list[str | Path]) -> None:
        self._search_paths = [Path(p) for p in search_paths]
        self._cache: dict[str, tuple[SkillMetadata, str, str]] = {}

    def discover(self) -> list[SkillMetadata]:
        self._cache.clear()
        results: list[SkillMetadata] = []

        for base in self._search_paths:
            if not base.is_dir():
                logger.info("skill_path_not_found", path=str(base))
                continue

            for skill_dir in sorted(base.iterdir()):
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.is_file():
                    continue

                parsed = _parse_skill_file(skill_file)
                if parsed is None:
                    continue

                metadata, body = parsed
                if metadata.name in self._cache:
                    logger.warning(
                        "skill_duplicate_name",
                        name=metadata.name,
                        path=str(skill_file),
                        existing=self._cache[metadata.name][2],
                    )
                    continue

                self._cache[metadata.name] = (metadata, body, str(skill_file))
                results.append(metadata)

        logger.info("skills_discovered", count=len(results))
        return results

    def load(self, name: str) -> SkillContent | None:
        entry = self._cache.get(name)
        if entry is None:
            return None
        metadata, body, source_path = entry
        return SkillContent(metadata=metadata, body=body, source_path=source_path)
