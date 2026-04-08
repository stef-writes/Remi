"""Tests for the CLI JSON envelope (shell/cli/output.py).

Verifies the structured envelope format that all CLI commands produce.
"""

from __future__ import annotations

import json

from remi.shell.cli.output import error, success


def test_success_envelope_structure() -> None:
    """Success envelope has status, data, and metadata."""
    env = success({"managers": [1, 2]}, command="remi portfolio managers")

    assert env["status"] == "success"
    assert env["data"] == {"managers": [1, 2]}
    assert env["metadata"]["command"] == "remi portfolio managers"
    assert env["metadata"]["_schema_version"] == "1.0"
    assert "timestamp" in env["metadata"]


def test_success_envelope_is_json_serializable() -> None:
    """Success envelope can be serialized to JSON."""
    env = success([{"id": "m1", "name": "Jake"}], command="remi portfolio managers")
    text = json.dumps(env, default=str)
    parsed = json.loads(text)

    assert parsed["status"] == "success"
    assert len(parsed["data"]) == 1


def test_error_envelope_structure() -> None:
    """Error envelope has status, error object, and metadata."""
    env = error(
        "MANAGER_NOT_FOUND",
        "No manager found with ID 'mgr-999'",
        command="remi portfolio manager-review",
        details={"provided_id": "mgr-999"},
    )

    assert env["status"] == "error"
    assert env["error"]["code"] == "MANAGER_NOT_FOUND"
    assert env["error"]["message"] == "No manager found with ID 'mgr-999'"
    assert env["error"]["details"]["provided_id"] == "mgr-999"
    assert env["metadata"]["command"] == "remi portfolio manager-review"


def test_error_envelope_without_details() -> None:
    """Error envelope works without details."""
    env = error("NOT_FOUND", "Gone", command="remi test")

    assert env["error"]["details"] == {}


def test_success_with_list_data() -> None:
    """Success envelope works with list data (common for list commands)."""
    data = [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]
    env = success(data, command="remi portfolio managers")

    assert isinstance(env["data"], list)
    assert len(env["data"]) == 3
