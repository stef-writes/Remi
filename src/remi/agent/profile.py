"""DomainProfile — typed operational tuning injected by the product layer.

Where DomainTBox declares "what things mean" (signals, thresholds, policies),
DomainProfile declares "how to operate on them" — name fields for retrieval,
parser patterns for ingestion, tool description hints, agent workforce
manifests, and empty-state labels.

The type lives in ``agent/`` so the agent layer can depend on it.
The builder lives in the domain layer (e.g. ``domain/profile.py``).
The container wires builder → profile → consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DomainProfile:
    """Domain-specific operational configuration consumed generically by agent/.

    Each field has a sensible default so agent/ works out of the box
    without a domain layer wired in.
    """

    name_fields: tuple[str, ...] = ("name",)
    """Metadata fields that contain entity names for keyword retrieval."""

    metadata_skip_patterns: tuple[str, ...] = ()
    """Regex patterns for report header rows that should be skipped during parsing."""

    empty_state_label: str = "monitored entities"
    """What to call the monitored universe when no signals are active."""

    scope_entity_type: str = ""
    """The primary scoping entity label (e.g. 'PropertyManager')."""

    tool_hints: dict[str, str] = field(default_factory=dict)
    """Tool-name → supplemental description text appended to the generic description."""

    available_agents: dict[str, str] = field(default_factory=dict)
    """Agent workforce: name → description for the delegation tool."""

    api_path_examples: str = ""
    """Example API paths appended to the http_request tool description."""

    data_bridge_hint: str = ""
    """Supplemental description for what ``remi_data`` exposes in the sandbox."""
