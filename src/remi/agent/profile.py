"""DomainProfile — typed operational tuning injected by the product layer.

Where DomainTBox declares "what things mean" (signals, thresholds, policies),
DomainProfile declares "how to operate on them" — name fields for retrieval,
parser patterns for ingestion, tool description hints, and empty-state labels.

The type lives in ``agent/`` so the agent layer can depend on it.
The builder lives in ``application/profile.py`` (``build_re_profile``).
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

    section_labels: frozenset[str] = frozenset()
    """Section-label values that identify context rows in hierarchical reports."""

    empty_state_label: str = "monitored entities"
    """What to call the monitored universe when no signals are active."""

    scope_entity_type: str = ""
    """The primary scoping entity label (e.g. 'Organization')."""

    tool_hints: dict[str, str] = field(default_factory=dict)
    """Tool-name → supplemental description text.  Currently unused (CLI-first
    architecture removed function-calling domain tools).  Retained for forward
    compat if kernel tools gain domain overlays."""

    api_path_examples: str = ""
    """Unused.  Previously provided example API paths for the HTTP tool."""
