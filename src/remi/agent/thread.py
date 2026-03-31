"""Thread construction and formatting utilities for agent conversations."""

from __future__ import annotations

import json
from typing import Any

from remi.agent.base import Message
from remi.agent.config import AgentConfig


def trim_thread(thread: list[Message], max_turns: int) -> list[Message]:
    """Apply a sliding window to keep only the last *max_turns* user/assistant pairs.

    System messages at the head are preserved unconditionally. If any
    conversational messages are removed, a short notice is inserted after the
    first system message so the model knows history was truncated.

    A "turn" is one user message plus one assistant message (2 messages).
    """
    if max_turns <= 0:
        return thread

    system_prefix: list[Message] = []
    conversation: list[Message] = []
    for msg in thread:
        if not conversation and msg.role == "system":
            system_prefix.append(msg)
        else:
            conversation.append(msg)

    max_messages = max_turns * 2
    if len(conversation) <= max_messages:
        return thread

    trimmed_count = len(conversation) - max_messages
    kept = conversation[-max_messages:]

    notice = Message(
        role="system",
        content=(
            f"[Earlier conversation history was trimmed for context limits. "
            f"{trimmed_count} messages removed.]"
        ),
    )
    return system_prefix + [notice] + kept


def build_initial_thread(cfg: AgentConfig, inputs: dict[str, Any]) -> list[Message]:
    """Build the initial message thread from config and inputs."""
    thread: list[Message] = []
    thread.append(Message(role="system", content=cfg.system_prompt))

    upstream_thread = inputs.get("thread")
    if isinstance(upstream_thread, list) and upstream_thread:
        for item in upstream_thread:
            if isinstance(item, Message):
                thread.append(item)
            elif isinstance(item, dict):
                thread.append(Message(**item))
    elif cfg.input_template:
        flat = _flatten_inputs(inputs)
        try:
            rendered = cfg.input_template.format(**flat)
        except KeyError:
            rendered = cfg.input_template.format(input=json.dumps(flat, default=str))
        thread.append(Message(role="user", content=rendered))
    else:
        content = _summarize_inputs(inputs)
        thread.append(Message(role="user", content=content))

    return thread


def format_output(thread: list[Message], cfg: AgentConfig) -> Any:
    """Extract the final output from the thread in the format the config demands."""
    if cfg.output_contract == "conversation":
        return [msg.model_dump() for msg in thread]
    return last_assistant_content(thread)


def last_assistant_content(thread: list[Message]) -> Any:
    """Return the content of the last assistant message, or None."""
    for msg in reversed(thread):
        if msg.role == "assistant":
            return msg.content
    return None


def try_parse_json(text: str | Any) -> Any:
    """Attempt to parse text as JSON; return original on failure."""
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _flatten_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, val in inputs.items():
        safe_key = key.replace("-", "_")
        if isinstance(val, dict):
            flat.update(val)
        flat[safe_key] = val
        flat[key] = val if not isinstance(val, (dict, list)) else json.dumps(val, default=str)
    if len(inputs) == 1:
        flat["input"] = next(iter(inputs.values()))
    return flat


def _summarize_inputs(inputs: dict[str, Any]) -> str:
    parts = []
    for key, val in inputs.items():
        if isinstance(val, (dict, list)):
            parts.append(f"{key}: {json.dumps(val, default=str)}")
        else:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)
