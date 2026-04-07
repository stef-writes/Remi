"""Analysis tools — ``python`` and ``bash`` for agent code execution.

Two tools give the agent a complete analytical environment:

- ``python`` — persistent Python session (variables survive between calls)
- ``bash`` — one-shot shell commands
"""

from __future__ import annotations

from typing import Any

from remi.agent.sandbox.types import Sandbox
from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry

_DEFAULT_SESSION = "agent-default"


async def _ensure_session(sandbox: Sandbox, session_id: str) -> None:
    session = await sandbox.get_session(session_id)
    if session is None:
        await sandbox.create_session(session_id)


class AnalysisToolProvider(ToolProvider):
    """Registers ``python`` and ``bash`` tools backed by a sandbox."""

    def __init__(self, sandbox: Sandbox, *, sdk_hint: str = "") -> None:
        self._sandbox = sandbox
        self._sdk_hint = sdk_hint

    def register(self, registry: ToolRegistry) -> None:
        sandbox = self._sandbox

        # -- python (persistent session) ----------------------------------------

        python_desc = (
            "Execute Python code in a persistent session. "
            "Variables, imports, and DataFrames survive between calls. "
            "pandas, numpy, scipy, matplotlib, statsmodels, and scikit-learn "
            "are available. "
        )
        if self._sdk_hint:
            python_desc += self._sdk_hint + " "
        python_desc += (
            "Print results to stdout. "
            "Use open() for file I/O — no separate file tools needed."
        )

        async def exec_python(args: dict[str, Any]) -> Any:
            code = args.get("code", "")
            if not code:
                return {"error": "No code provided"}
            timeout = min(int(args.get("timeout", 120)), 300)
            session_id = args.get("session_id", _DEFAULT_SESSION)
            await _ensure_session(sandbox, session_id)

            result = await sandbox.exec_python(session_id, code, timeout_seconds=timeout)
            out: dict[str, Any] = {
                "status": result.status.value,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_ms": round(result.duration_ms, 1),
            }
            if result.files_created:
                out["files_created"] = result.files_created
            if result.error:
                out["error"] = result.error
            return out

        registry.register(
            "python",
            exec_python,
            ToolDefinition(
                name="python",
                description=python_desc,
                args=[
                    ToolArg(
                        name="code",
                        description="Python source code to execute",
                        required=True,
                    ),
                    ToolArg(
                        name="timeout",
                        description="Timeout in seconds (default 120, max 300)",
                    ),
                ],
            ),
        )

        # -- bash (one-shot shell) -----------------------------------------------

        async def exec_bash(args: dict[str, Any]) -> Any:
            command = args.get("command", "")
            if not command:
                return {"error": "No command provided"}
            timeout = min(int(args.get("timeout", 30)), 120)
            session_id = args.get("session_id", _DEFAULT_SESSION)
            await _ensure_session(sandbox, session_id)

            result = await sandbox.exec_shell(session_id, command, timeout_seconds=timeout)
            out: dict[str, Any] = {
                "status": result.status.value,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_ms": round(result.duration_ms, 1),
            }
            if result.error:
                out["error"] = result.error
            return out

        registry.register(
            "bash",
            exec_bash,
            ToolDefinition(
                name="bash",
                description=(
                    "Run a shell command. Use for CLI tools, file listing (ls), "
                    "file reading (cat), and general shell operations."
                ),
                args=[
                    ToolArg(
                        name="command",
                        description="Shell command to execute",
                        required=True,
                    ),
                    ToolArg(
                        name="timeout",
                        description="Timeout in seconds (default 30, max 120)",
                    ),
                ],
            ),
        )
