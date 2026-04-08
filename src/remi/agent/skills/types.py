"""Skill types — metadata and content models for filesystem-based playbooks.

A skill is a markdown file with YAML frontmatter that teaches an agent
how to perform a specific analytical workflow using ``remi`` CLI commands.
Skills are discovered at agent startup and injected into the system prompt
as a capability catalog.
"""

from __future__ import annotations

from enum import StrEnum, unique

from pydantic import BaseModel, Field


@unique
class SkillScope(StrEnum):
    """Where this skill applies."""

    GLOBAL = "global"
    ENTITY = "entity"


@unique
class SkillTrigger(StrEnum):
    """How the agent decides to use this skill."""

    ON_DEMAND = "on_demand"
    AUTO = "auto"


class SkillMetadata(BaseModel, frozen=True):
    """Parsed from YAML frontmatter of a SKILL.md file."""

    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    scope: SkillScope = SkillScope.GLOBAL
    trigger: SkillTrigger = SkillTrigger.ON_DEMAND
    required_capabilities: list[str] = Field(default_factory=list)
    version: str = "1"


class SkillContent(BaseModel, frozen=True):
    """Full skill: metadata + body text loaded on demand."""

    metadata: SkillMetadata
    body: str
    source_path: str = ""
