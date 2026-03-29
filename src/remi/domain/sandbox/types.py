"""Sandbox types — execution results and session metadata."""

from __future__ import annotations

from datetime import datetime, UTC
from enum import Enum, unique
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


@unique
class ExecStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ExecResult(BaseModel, frozen=True):
    """Result of executing code or a command in the sandbox."""

    status: ExecStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0
    files_created: list[str] = Field(default_factory=list)
    error: str | None = None


class SandboxSession(BaseModel):
    """Tracks an active sandbox session for an agent."""

    session_id: str
    working_dir: str
    created_at: datetime = Field(default_factory=_utcnow)
    exec_count: int = 0
    files: list[str] = Field(default_factory=list)
