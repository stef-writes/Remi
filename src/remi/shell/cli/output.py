"""Structured JSON envelope for all CLI output.

Every ``remi`` CLI command outputs a consistent JSON envelope when
``--json`` is passed (or when piped/non-interactive). This module
provides ``success()`` and ``error()`` helpers that wrap data in
the standard format::

    {"status": "success", "data": ..., "metadata": {...}}
    {"status": "error", "error": {...}, "metadata": {...}}
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import typer

_SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def success(data: Any, *, command: str) -> dict[str, Any]:
    """Wrap *data* in the standard success envelope."""
    return {
        "status": "success",
        "data": data,
        "metadata": {
            "command": command,
            "timestamp": _now_iso(),
            "_schema_version": _SCHEMA_VERSION,
        },
    }


def error(
    code: str,
    message: str,
    *,
    command: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap an error in the standard error envelope."""
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "metadata": {
            "command": command,
            "timestamp": _now_iso(),
            "_schema_version": _SCHEMA_VERSION,
        },
    }


def emit(envelope: dict[str, Any]) -> None:
    """Print the envelope as JSON to stdout."""
    typer.echo(json.dumps(envelope, default=str, indent=2))


def emit_success(data: Any, *, command: str) -> None:
    """Shorthand: build a success envelope and print it."""
    emit(success(data, command=command))


def emit_error(
    code: str,
    message: str,
    *,
    command: str,
    details: dict[str, Any] | None = None,
    exit_code: int = 1,
) -> None:
    """Print an error envelope and raise SystemExit."""
    emit(error(code, message, command=command, details=details))
    raise typer.Exit(code=exit_code)
