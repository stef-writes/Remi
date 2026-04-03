"""Text utilities shared across the REMI codebase."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Token estimation — no external dependencies
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Return approximate token count for *text*."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate *text* to fit within *max_tokens*, breaking on a line boundary."""
    if estimate_tokens(text) <= max_tokens:
        return text
    char_budget = max_tokens * CHARS_PER_TOKEN
    truncated = text[:char_budget]
    last_nl = truncated.rfind("\n")
    if last_nl > char_budget // 2:
        truncated = truncated[:last_nl]
    return truncated


def slugify(text: str) -> str:
    """Convert a string to a stable slug/entity-ID safe form."""
    return re.sub(r"[^a-z0-9:]+", "-", text.lower().strip()).strip("-")


def normalize_name(name: str) -> str:
    """Normalize a person or entity name: collapse internal whitespace, title-case."""
    return " ".join(name.split())
