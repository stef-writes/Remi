"""Sandbox tools — the agent's interface to code execution and file I/O.

Five tools give the agent a complete analytical environment:

- ``sandbox_exec`` — run shell commands (``remi`` CLI, etc.)
- ``sandbox_exec_python`` — write and execute Python code
- ``sandbox_write_file`` — persist files (reports, data, intermediates)
- ``sandbox_read_file`` — read file contents back
- ``sandbox_list_files`` — see what's in the working directory
"""

from __future__ import annotations

from typing import Any

from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry
from remi.agent.sandbox.types import Sandbox

_DEFAULT_SESSION = "agent-default"


async def _ensure_session(sandbox: Sandbox, session_id: str) -> None:
    session = await sandbox.get_session(session_id)
    if session is None:
        await sandbox.create_session(session_id)


class SandboxToolProvider(ToolProvider):
    def __init__(self, sandbox: Sandbox, *, data_bridge_hint: str = "") -> None:
        self._sandbox = sandbox
        self._data_bridge_hint = data_bridge_hint

    def register(self, registry: ToolRegistry) -> None:
        sandbox = self._sandbox

        async def exec_shell(args: dict[str, Any]) -> Any:
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
            "sandbox_exec",
            exec_shell,
            ToolDefinition(
                name="sandbox_exec",
                description=(
                    "Run a shell command in your sandbox. Use for `remi` CLI commands "
                    "(signals, ontology queries, quick lookups) and general shell operations."
                ),
                args=[
                    ToolArg(name="command", description="Shell command to execute", required=True),
                    ToolArg(name="timeout", description="Timeout in seconds (default 30, max 120)"),
                ],
            ),
        )

        python_desc = (
            "Write and execute Python code for data analysis. "
            "pandas, numpy, scipy, matplotlib, statsmodels, and scikit-learn "
            "are available. "
        )
        if self._data_bridge_hint:
            python_desc += self._data_bridge_hint + " "
        python_desc += (
            "Print results to stdout. Files written to the working directory "
            "are preserved across calls."
        )

        async def exec_python(args: dict[str, Any]) -> Any:
            code = args.get("code", "")
            if not code:
                return {"error": "No code provided"}
            timeout = min(int(args.get("timeout", 60)), 300)
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
            "sandbox_exec_python",
            exec_python,
            ToolDefinition(
                name="sandbox_exec_python",
                description=python_desc,
                args=[
                    ToolArg(
                        name="code", description="Python source code to execute", required=True
                    ),
                    ToolArg(name="timeout", description="Timeout in seconds (default 60, max 300)"),
                ],
            ),
        )

        async def write_file(args: dict[str, Any]) -> Any:
            filename = args.get("filename", "")
            content = args.get("content", "")
            if not filename:
                return {"error": "No filename provided"}
            session_id = args.get("session_id", _DEFAULT_SESSION)
            await _ensure_session(sandbox, session_id)

            saved_name = await sandbox.write_file(session_id, filename, content)
            return {"status": "success", "filename": saved_name}

        registry.register(
            "sandbox_write_file",
            write_file,
            ToolDefinition(
                name="sandbox_write_file",
                description=(
                    "Write a file to the sandbox working directory. Use for saving "
                    "reports, analysis results, intermediate data, or any output."
                ),
                args=[
                    ToolArg(
                        name="filename", description="Name of the file to write", required=True
                    ),
                    ToolArg(name="content", description="File contents", required=True),
                ],
            ),
        )

        async def read_file(args: dict[str, Any]) -> Any:
            filename = args.get("filename", "")
            if not filename:
                return {"error": "No filename provided"}
            session_id = args.get("session_id", _DEFAULT_SESSION)
            await _ensure_session(sandbox, session_id)

            content = await sandbox.read_file(session_id, filename)
            if content is None:
                return {"error": f"File '{filename}' not found"}
            return {"status": "success", "filename": filename, "content": content}

        registry.register(
            "sandbox_read_file",
            read_file,
            ToolDefinition(
                name="sandbox_read_file",
                description="Read a file from the sandbox working directory.",
                args=[
                    ToolArg(
                        name="filename", description="Name of the file to read", required=True
                    ),
                ],
            ),
        )

        async def list_files(args: dict[str, Any]) -> Any:
            session_id = args.get("session_id", _DEFAULT_SESSION)
            await _ensure_session(sandbox, session_id)

            files = await sandbox.list_files(session_id)
            return {"status": "success", "files": files, "count": len(files)}

        registry.register(
            "sandbox_list_files",
            list_files,
            ToolDefinition(
                name="sandbox_list_files",
                description="List all files in the sandbox working directory.",
                args=[],
            ),
        )


# COMPAT: tests and existing code call this directly
def register_sandbox_tools(
    registry: ToolRegistry,
    *,
    sandbox: Sandbox | None = None,
    data_bridge_hint: str = "",
) -> None:
    if sandbox is None:
        return
    SandboxToolProvider(sandbox, data_bridge_hint=data_bridge_hint).register(registry)
