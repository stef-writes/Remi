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

from remi.models.sandbox import Sandbox
from remi.models.tools import ToolArg, ToolDefinition, ToolRegistry

_DEFAULT_SESSION = "agent-default"


async def _ensure_session(sandbox: Sandbox, session_id: str) -> None:
    session = await sandbox.get_session(session_id)
    if session is None:
        await sandbox.create_session(session_id)


def register_sandbox_tools(
    registry: ToolRegistry,
    *,
    sandbox: Sandbox | None = None,
) -> None:
    if sandbox is None:
        return

    # -- sandbox_exec: shell commands -----------------------------------------

    async def exec_shell(args: dict[str, Any]) -> Any:
        command = args.get("command", "")
        if not command:
            return {"error": "No command provided"}
        timeout = min(int(args.get("timeout", 30)), 120)
        session_id = args.get("session_id", _DEFAULT_SESSION)
        await _ensure_session(sandbox, session_id)

        result = await sandbox.exec_shell(session_id, command, timeout_seconds=timeout)
        return {
            "status": result.status.value,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": round(result.duration_ms, 1),
            "error": result.error,
        }

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

    # -- sandbox_exec_python: code execution ----------------------------------

    async def exec_python(args: dict[str, Any]) -> Any:
        code = args.get("code", "")
        if not code:
            return {"error": "No code provided"}
        timeout = min(int(args.get("timeout", 60)), 300)
        session_id = args.get("session_id", _DEFAULT_SESSION)
        await _ensure_session(sandbox, session_id)

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
                "Write and execute Python code for data analysis. "
                "pandas and numpy are available. Use `import remi_data` to query "
                "live platform data (properties, units, leases, maintenance, signals). "
                "Print results to stdout. Files written to the working directory "
                "are preserved across calls."
            ),
            args=[
                ToolArg(name="code", description="Python source code to execute", required=True),
                ToolArg(name="timeout", description="Timeout in seconds (default 60, max 300)"),
            ],
        ),
    )

    # -- sandbox_write_file: persist files ------------------------------------

    async def write_file(args: dict[str, Any]) -> Any:
        filename = args.get("filename", "")
        content = args.get("content", "")
        if not filename:
            return {"error": "No filename provided"}
        session_id = args.get("session_id", _DEFAULT_SESSION)
        await _ensure_session(sandbox, session_id)

        try:
            saved_name = await sandbox.write_file(session_id, filename, content)
            return {"status": "success", "filename": saved_name}
        except Exception as exc:
            return {"error": str(exc)}

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
                ToolArg(name="filename", description="Name of the file to write", required=True),
                ToolArg(name="content", description="File contents", required=True),
            ],
        ),
    )

    # -- sandbox_read_file: read files back -----------------------------------

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
                ToolArg(name="filename", description="Name of the file to read", required=True),
            ],
        ),
    )

    # -- sandbox_list_files: directory listing ---------------------------------

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
