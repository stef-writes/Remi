"""Agent context — perception, intent classification, and context rendering.

Public API::

    from remi.agent.context import build_context_builder, WorldState, EntityViewEnricher
"""

from remi.agent.context.builder import build_context_builder
from remi.agent.context.enricher import EntityViewEnricher
from remi.agent.context.frame import WorldState

__all__ = [
    "WorldState",
    "EntityViewEnricher",
    "build_context_builder",
]
