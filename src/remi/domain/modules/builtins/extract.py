"""Context extractor — bridges a conversation thread to a structured output contract."""

from __future__ import annotations

import json
from typing import Any

from remi.domain.modules.base import BaseModule, ModuleOutput
from remi.runtime.context.runtime_context import RuntimeContext


class ContextExtractorModule(BaseModule):
    """Extracts structured data from a conversation thread.

    Config keys:
        target_contract: the output contract string (e.g. "dashboard_card", "table_view")
        field:           optional — pull a specific field from the last assistant message
        transform:       optional — a JSON template string; ``input`` is the parsed content
    """

    kind = "extract"

    async def run(self, inputs: dict[str, Any], context: RuntimeContext) -> ModuleOutput:
        target_contract = self.config.get("target_contract", "raw")
        field = self.config.get("field")

        content = _get_last_assistant_content(inputs)

        if isinstance(content, str):
            content = _try_parse_json(content)

        if field and isinstance(content, dict):
            content = content.get(field, content)

        if transform := self.config.get("transform"):
            content = _apply_transform(transform, content)

        return ModuleOutput(
            value=content,
            contract=target_contract,
        )


def _get_last_assistant_content(inputs: dict[str, Any]) -> Any:
    thread = inputs.get("thread")
    if isinstance(thread, list):
        for msg in reversed(thread):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                return msg.get("content")
    for val in inputs.values():
        if isinstance(val, list):
            for msg in reversed(val):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content")
        else:
            return val
    return None


def _try_parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _apply_transform(template: str, data: Any) -> Any:
    """Simple template evaluation — replaces ``input`` references with data."""
    try:
        result = eval(template, {"__builtins__": {}}, {"input": data})  # noqa: S307
        return result
    except Exception:
        return data
