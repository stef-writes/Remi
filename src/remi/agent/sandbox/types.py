"""Sandbox execution ports — ABC and result types.

Defines the ``Sandbox`` interface and its associated DTOs. Concrete
backends (e.g. ``LocalSandbox``) implement this ABC. Consumers depend
on the port, never on a concrete backend.
"""

from __future__ import annotations

import abc
from datetime import UTC, datetime
from enum import StrEnum, unique

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


@unique
class ExecStatus(StrEnum):
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


class Sandbox(abc.ABC):
    """Isolated execution environment for agent-written code.

    Each session gets its own working directory. Code runs in an isolated
    process (subprocess or container) with restricted access: no host
    filesystem outside the sandbox dir, resource limits enforced.
    """

    @abc.abstractmethod
    async def create_session(
        self,
        session_id: str | None = None,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> SandboxSession: ...

    @abc.abstractmethod
    async def exec_python(
        self,
        session_id: str,
        code: str,
        *,
        timeout_seconds: int = 30,
    ) -> ExecResult: ...

    @abc.abstractmethod
    async def exec_shell(
        self,
        session_id: str,
        command: str,
        *,
        timeout_seconds: int = 30,
    ) -> ExecResult: ...

    @abc.abstractmethod
    async def write_file(
        self,
        session_id: str,
        filename: str,
        content: str,
    ) -> str: ...

    @abc.abstractmethod
    async def read_file(
        self,
        session_id: str,
        filename: str,
    ) -> str | None: ...

    @abc.abstractmethod
    async def list_files(self, session_id: str) -> list[str]: ...

    @abc.abstractmethod
    async def get_session(self, session_id: str) -> SandboxSession | None: ...

    @abc.abstractmethod
    async def destroy_session(self, session_id: str) -> None: ...
