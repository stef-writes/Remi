"""Tests for thread construction and trimming utilities."""

from __future__ import annotations

from remi.agent.thread import trim_thread
from remi.models.chat import Message


def _msg(role: str, content: str) -> Message:
    return Message(role=role, content=content)


def test_trim_thread_noop_when_short() -> None:
    thread = [
        _msg("system", "You are helpful."),
        _msg("user", "Hello"),
        _msg("assistant", "Hi there!"),
    ]
    result = trim_thread(thread, max_turns=10)
    assert result == thread


def test_trim_thread_preserves_system_prefix() -> None:
    thread = [
        _msg("system", "System prompt"),
        _msg("system", "Extra context"),
        *[_msg("user", f"u{i}") for i in range(20)],
        *[_msg("assistant", f"a{i}") for i in range(20)],
    ]
    result = trim_thread(thread, max_turns=5)
    assert result[0].content == "System prompt"
    assert result[1].content == "Extra context"
    assert "[Earlier conversation history" in str(result[2].content)


def test_trim_thread_keeps_last_n_turns() -> None:
    sys_msg = _msg("system", "System prompt")
    conversation = []
    for i in range(15):
        conversation.append(_msg("user", f"user-{i}"))
        conversation.append(_msg("assistant", f"assistant-{i}"))
    thread = [sys_msg] + conversation

    result = trim_thread(thread, max_turns=5)

    non_system = [m for m in result if m.role != "system"]
    assert len(non_system) == 10
    assert non_system[0].content == "user-10"
    assert non_system[-1].content == "assistant-14"


def test_trim_thread_notice_message_count() -> None:
    sys_msg = _msg("system", "Prompt")
    conversation = []
    for i in range(10):
        conversation.append(_msg("user", f"u{i}"))
        conversation.append(_msg("assistant", f"a{i}"))
    thread = [sys_msg] + conversation

    result = trim_thread(thread, max_turns=3)

    notice = result[1]
    assert notice.role == "system"
    assert "14 messages removed" in str(notice.content)


def test_trim_thread_zero_turns_returns_original() -> None:
    thread = [
        _msg("system", "Prompt"),
        _msg("user", "Hello"),
        _msg("assistant", "Hi"),
    ]
    result = trim_thread(thread, max_turns=0)
    assert result == thread


def test_trim_thread_exact_boundary() -> None:
    sys_msg = _msg("system", "Prompt")
    conversation = []
    for i in range(5):
        conversation.append(_msg("user", f"u{i}"))
        conversation.append(_msg("assistant", f"a{i}"))
    thread = [sys_msg] + conversation

    result = trim_thread(thread, max_turns=5)
    assert result == thread


def test_trim_thread_multiple_system_messages_preserved() -> None:
    thread = [
        _msg("system", "Base prompt"),
        _msg("system", "Domain context"),
        _msg("system", "Signal summary"),
        *[_msg("user", f"u{i}") for i in range(20)],
    ]
    result = trim_thread(thread, max_turns=5)
    assert result[0].content == "Base prompt"
    assert result[1].content == "Domain context"
    assert result[2].content == "Signal summary"
    assert result[3].role == "system"
    assert "trimmed" in str(result[3].content).lower()
