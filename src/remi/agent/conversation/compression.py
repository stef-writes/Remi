"""Tool result compression — keeps the agent thread lean.

Large tool results (workflow reviews, HTTP responses, delegation output)
are compressed before being appended to the thread.  This prevents
quadratic token growth when the agent makes multiple tool calls:
each subsequent LLM call re-reads the *entire* thread, so a 5K-token
tool result read 10 times costs 50K tokens of pure waste.

Strategy:
- Results under the token threshold pass through unchanged.
- Over the threshold: extract a structured summary (top-level keys,
  row counts, numeric aggregates) and truncate the raw payload.
  The summary preserves enough signal for the LLM to reason without
  needing the full JSON.
"""

from __future__ import annotations

import json
from typing import Any

_TOKEN_THRESHOLD = 500
_CHARS_PER_TOKEN = 4
_MAX_SUMMARY_CHARS = 1600


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def compress_tool_result(tool_name: str, result: Any) -> Any:
    """Compress a tool result if it exceeds the token budget.

    Returns the original result if small enough, or a compact summary
    dict with key metrics preserved and the raw payload truncated.
    """
    if isinstance(result, str):
        if _estimate_tokens(result) <= _TOKEN_THRESHOLD:
            return result
        return _truncate_string(result)

    if isinstance(result, (int, float, bool)) or result is None:
        return result

    serialized = json.dumps(result, default=str)
    if _estimate_tokens(serialized) <= _TOKEN_THRESHOLD:
        return result

    return _summarize_structured(tool_name, result, serialized)


def _truncate_string(text: str) -> str:
    limit = _TOKEN_THRESHOLD * _CHARS_PER_TOKEN
    return text[:limit] + f"\n\n[Truncated — {len(text)} chars total, showing first {limit}]"


def _summarize_structured(tool_name: str, result: Any, serialized: str) -> dict[str, Any]:
    """Build a compact summary of a large structured result."""
    summary: dict[str, Any] = {
        "_compressed": True,
        "_tool": tool_name,
        "_original_tokens": _estimate_tokens(serialized),
    }

    if isinstance(result, list):
        summary["_count"] = len(result)
        if result and isinstance(result[0], dict):
            summary["_keys"] = list(result[0].keys())
            summary["items"] = _extract_list_summary(result)
        else:
            summary["items"] = result[:5]
        return summary

    if isinstance(result, dict):
        if "error" in result:
            return result

        summary["_keys"] = list(result.keys())
        compressed_body: dict[str, Any] = {}

        for key, value in result.items():
            compressed_body[key] = _compress_value(key, value)

        summary["data"] = compressed_body
        return summary

    return summary


def _compress_value(key: str, value: Any) -> Any:
    """Compress a single value within a dict result."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, list):
        if not value:
            return []
        count = len(value)
        if count <= 3:
            return value
        if isinstance(value[0], dict):
            preview = _extract_list_summary(value, max_items=3)
            return {"_count": count, "_preview": preview}
        return {"_count": count, "_preview": value[:3]}

    if isinstance(value, dict):
        text = json.dumps(value, default=str)
        if _estimate_tokens(text) <= 100:
            return value
        scalars = {
            k: v for k, v in value.items() if isinstance(v, (str, int, float, bool)) or v is None
        }
        nested_summaries = {
            k: f"[{type(v).__name__}: {len(v)} items]"
            for k, v in value.items()
            if isinstance(v, (list, dict)) and k not in scalars
        }
        return {**scalars, **nested_summaries}

    return str(value)[:200]


def _extract_list_summary(items: list[dict[str, Any]], max_items: int = 5) -> list[dict[str, Any]]:
    """Extract the most informative fields from a list of dicts."""
    if not items:
        return []

    sample = items[:max_items]
    all_keys = list(items[0].keys())

    priority_keys = [
        k
        for k in all_keys
        if any(
            term in k.lower()
            for term in (
                "id",
                "name",
                "total",
                "balance",
                "rate",
                "count",
                "amount",
                "status",
                "score",
                "rank",
                "date",
            )
        )
    ]
    other_scalar_keys = [
        k
        for k in all_keys
        if k not in priority_keys and isinstance(items[0].get(k), (str, int, float, bool))
    ]
    keep_keys = (priority_keys + other_scalar_keys)[:12]

    if not keep_keys:
        keep_keys = all_keys[:8]

    return [{k: item.get(k) for k in keep_keys} for item in sample]
