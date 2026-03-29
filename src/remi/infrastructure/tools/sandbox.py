"""Sandbox tools — isolated code execution for agents.

Provides: sandbox_exec_python, sandbox_exec_shell, sandbox_write_file,
sandbox_read_file, sandbox_list_files.

Each agent gets a sandbox session (created on first use) with its own
working directory. Code runs in subprocess isolation with timeouts and
restricted environment.
"""

from __future__ import annotations

from typing import Any

from remi.domain.sandbox.ports import Sandbox
from remi.domain.tools.ports import ToolArg, ToolDefinition, ToolRegistry


_DEFAULT_SESSION = "agent-default"


def register_sandbox_tools(
    registry: ToolRegistry,
    *,
    sandbox: Sandbox | None = None,
) -> None:
    if sandbox is None:
        return

    # -- sandbox_exec_python ---------------------------------------------------

    async def exec_python(args: dict[str, Any]) -> Any:
        code = args.get("code", "")
        if not code:
            return {"error": "No code provided"}
        timeout = int(args.get("timeout", 30))
        session_id = args.get("session_id", _DEFAULT_SESSION)

        session = await sandbox.get_session(session_id)
        if session is None:
            session = await sandbox.create_session(session_id)

        result = await sandbox.exec_python(session_id, code, timeout_seconds=timeout)
        return {
            "status": result.status.value,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": round(result.duration_ms, 1),
            "files_created": result.files_created,
            "error": result.error,
        }

    registry.register(
        "sandbox_exec_python",
        exec_python,
        ToolDefinition(
            name="sandbox_exec_python",
            description=(
                "Execute Python code in an isolated sandbox. Use for data analysis, "
                "ML scripts, calculations, or any code that needs to run. The sandbox "
                "has pandas, numpy, and standard library available. Files written to "
                "the working directory persist across calls in the same session."
            ),
            args=[
                ToolArg(name="code", description="Python code to execute", required=True),
                ToolArg(name="timeout", description="Timeout in seconds (default 30, max 120)"),
                ToolArg(name="session_id", description="Sandbox session ID (default: auto)"),
            ],
        ),
    )

    # -- sandbox_exec_shell ----------------------------------------------------

    async def exec_shell(args: dict[str, Any]) -> Any:
        command = args.get("command", "")
        if not command:
            return {"error": "No command provided"}
        timeout = int(args.get("timeout", 30))
        session_id = args.get("session_id", _DEFAULT_SESSION)

        session = await sandbox.get_session(session_id)
        if session is None:
            session = await sandbox.create_session(session_id)

        result = await sandbox.exec_shell(session_id, command, timeout_seconds=timeout)
        return {
            "status": result.status.value,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": round(result.duration_ms, 1),
            "files_created": result.files_created,
            "error": result.error,
        }

    registry.register(
        "sandbox_exec_shell",
        exec_shell,
        ToolDefinition(
            name="sandbox_exec_shell",
            description=(
                "Execute a shell command in the sandbox. The command runs in the "
                "sandbox working directory with restricted permissions. Some commands "
                "(sudo, network tools) are blocked."
            ),
            args=[
                ToolArg(name="command", description="Shell command to execute", required=True),
                ToolArg(name="timeout", description="Timeout in seconds (default 30)"),
                ToolArg(name="session_id", description="Sandbox session ID"),
            ],
        ),
    )

    # -- sandbox_write_file ----------------------------------------------------

    async def write_file(args: dict[str, Any]) -> Any:
        filename = args.get("filename", "")
        content = args.get("content", "")
        if not filename:
            return {"error": "No filename provided"}
        session_id = args.get("session_id", _DEFAULT_SESSION)

        session = await sandbox.get_session(session_id)
        if session is None:
            session = await sandbox.create_session(session_id)

        name = await sandbox.write_file(session_id, filename, content)
        return {"written": name, "size_bytes": len(content.encode("utf-8"))}

    registry.register(
        "sandbox_write_file",
        write_file,
        ToolDefinition(
            name="sandbox_write_file",
            description="Write a file to the sandbox working directory.",
            args=[
                ToolArg(name="filename", description="File name (no paths, just name)", required=True),
                ToolArg(name="content", description="File content", required=True),
                ToolArg(name="session_id", description="Sandbox session ID"),
            ],
        ),
    )

    # -- sandbox_read_file -----------------------------------------------------

    async def read_file(args: dict[str, Any]) -> Any:
        filename = args.get("filename", "")
        if not filename:
            return {"error": "No filename provided"}
        session_id = args.get("session_id", _DEFAULT_SESSION)

        content = await sandbox.read_file(session_id, filename)
        if content is None:
            return {"error": f"File '{filename}' not found in sandbox"}
        return {"filename": filename, "content": content, "size_bytes": len(content.encode("utf-8"))}

    registry.register(
        "sandbox_read_file",
        read_file,
        ToolDefinition(
            name="sandbox_read_file",
            description="Read a file from the sandbox working directory.",
            args=[
                ToolArg(name="filename", description="File name to read", required=True),
                ToolArg(name="session_id", description="Sandbox session ID"),
            ],
        ),
    )

    # -- sandbox_list_files ----------------------------------------------------

    async def list_files(args: dict[str, Any]) -> Any:
        session_id = args.get("session_id", _DEFAULT_SESSION)
        files = await sandbox.list_files(session_id)
        return {"files": files, "count": len(files)}

    registry.register(
        "sandbox_list_files",
        list_files,
        ToolDefinition(
            name="sandbox_list_files",
            description="List files in the sandbox working directory.",
            args=[
                ToolArg(name="session_id", description="Sandbox session ID"),
            ],
        ),
    )
