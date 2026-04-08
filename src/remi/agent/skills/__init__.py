"""agent/skills — filesystem-based playbooks for agent capabilities.

Skills are markdown files with YAML frontmatter that teach agents how
to perform specific workflows.  The kernel provides discovery and
loading; the application layer provides the actual skill content.

Public API::

    from remi.agent.skills import FilesystemSkillDiscovery, SkillMetadata
"""

from remi.agent.skills.discovery import FilesystemSkillDiscovery, SkillDiscovery
from remi.agent.skills.types import SkillContent, SkillMetadata, SkillScope, SkillTrigger

__all__ = [
    "FilesystemSkillDiscovery",
    "SkillContent",
    "SkillDiscovery",
    "SkillMetadata",
    "SkillScope",
    "SkillTrigger",
]
