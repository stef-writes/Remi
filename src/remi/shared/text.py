"""Text utilities shared across the REMI codebase."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Convert a string to a stable slug/entity-ID safe form."""
    return re.sub(r"[^a-z0-9:]+", "-", text.lower().strip()).strip("-")


def manager_name_from_tag(tag: str) -> str:
    """Extract the person's name from a manager tag like 'Jake Kraus Management'."""
    suffixes = ("management", "mgmt", "properties", "property")
    name = tag.strip()
    lower = name.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    return name or tag
