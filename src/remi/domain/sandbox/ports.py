"""Sandbox port — interface for isolated code execution."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from remi.domain.sandbox.types import ExecResult, SandboxSession


class Sandbox(abc.ABC):
    """Isolated execution environment for agent-written code.

    Each session gets its own working directory. Code runs in a subprocess
    with restricted access: no host filesystem outside the sandbox dir,
    no network by default, resource limits enforced.
    """

    @abc.abstractmethod
    async def create_session(self, session_id: str | None = None) -> SandboxSession: ...

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
