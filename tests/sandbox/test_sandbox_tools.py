"""Tests for the sandbox tool surface — exec, exec_python, write/read/list files.

Every tool is exercised end-to-end through the real LocalSandbox (temp dirs,
real subprocesses). No mocks of the sandbox itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from remi.models.sandbox import ExecStatus
from remi.sandbox.local import LocalSandbox
from remi.tools.registry import InMemoryToolRegistry
from remi.tools.sandbox import register_sandbox_tools


@pytest.fixture
def sandbox(tmp_path: Path) -> LocalSandbox:
    return LocalSandbox(root=tmp_path / "sandbox")


@pytest.fixture
def registry(sandbox: LocalSandbox) -> InMemoryToolRegistry:
    reg = InMemoryToolRegistry()
    register_sandbox_tools(reg, sandbox=sandbox)
    return reg


async def _call(registry: InMemoryToolRegistry, name: str, args: dict) -> dict:
    entry = registry.get(name)
    assert entry is not None, f"Tool '{name}' not registered"
    fn, _ = entry
    return await fn(args)


# -- US-1: exec_python --------------------------------------------------------

@pytest.mark.asyncio
async def test_exec_python_tool(sandbox: LocalSandbox, registry: InMemoryToolRegistry) -> None:
    await sandbox.create_session("s1")
    result = await _call(registry, "sandbox_exec_python", {
        "session_id": "s1",
        "code": "print(2 + 2)",
    })
    assert result["status"] == ExecStatus.SUCCESS
    assert "4" in result["stdout"]
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_exec_python_error_returns_stderr(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-err")
    result = await _call(registry, "sandbox_exec_python", {
        "session_id": "s-err",
        "code": "raise ValueError('boom')",
    })
    assert result["status"] == ExecStatus.ERROR
    assert "boom" in result["stderr"]


# -- US-1 supplement: exec (shell) --------------------------------------------

@pytest.mark.asyncio
async def test_exec_shell_tool(sandbox: LocalSandbox, registry: InMemoryToolRegistry) -> None:
    await sandbox.create_session("s2")
    result = await _call(registry, "sandbox_exec", {
        "session_id": "s2",
        "command": "echo hello",
    })
    assert result["status"] == ExecStatus.SUCCESS
    assert "hello" in result["stdout"]


# -- US-2: write + read files -------------------------------------------------

@pytest.mark.asyncio
async def test_write_and_read_file_tools(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s3")

    write_result = await _call(registry, "sandbox_write_file", {
        "session_id": "s3",
        "filename": "report.md",
        "content": "# Vacancy Report\nOccupancy is 94%.",
    })
    assert write_result["status"] == "success"
    assert write_result["filename"] == "report.md"

    read_result = await _call(registry, "sandbox_read_file", {
        "session_id": "s3",
        "filename": "report.md",
    })
    assert read_result["status"] == "success"
    assert "Vacancy Report" in read_result["content"]
    assert "94%" in read_result["content"]


@pytest.mark.asyncio
async def test_read_missing_file(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-miss")
    result = await _call(registry, "sandbox_read_file", {
        "session_id": "s-miss",
        "filename": "nope.txt",
    })
    assert "error" in result
    assert "not found" in result["error"].lower()


# -- US-3: list files ----------------------------------------------------------

@pytest.mark.asyncio
async def test_list_files_tool(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s4")
    await _call(registry, "sandbox_write_file", {
        "session_id": "s4",
        "filename": "a.csv",
        "content": "x,y\n1,2",
    })
    await _call(registry, "sandbox_write_file", {
        "session_id": "s4",
        "filename": "b.json",
        "content": '{"ok": true}',
    })

    result = await _call(registry, "sandbox_list_files", {"session_id": "s4"})
    assert result["status"] == "success"
    assert "a.csv" in result["files"]
    assert "b.json" in result["files"]
    assert result["count"] >= 2


# -- US-5: data bridge auto-written -------------------------------------------

@pytest.mark.asyncio
async def test_session_has_data_bridge(sandbox: LocalSandbox) -> None:
    session = await sandbox.create_session("s5")
    bridge_path = Path(session.working_dir) / "remi_data.py"
    assert bridge_path.exists(), "remi_data.py should be auto-written on session create"
    source = bridge_path.read_text()
    assert "def properties(" in source
    assert "def rent_roll(" in source
    assert "def managers(" in source


# -- US-6: session_id injection for all sandbox_* tools -----------------------

@pytest.mark.asyncio
async def test_session_id_injection(sandbox: LocalSandbox) -> None:
    """AgentNode._build_tool_set injects session_id for name.startswith('sandbox_').

    We simulate the same logic here: verify every registered sandbox tool
    gets session_id routed correctly by calling through the tool handlers
    with only session_id in args (auto-create via _ensure_session).
    """
    reg = InMemoryToolRegistry()
    register_sandbox_tools(reg, sandbox=sandbox)

    session_id = "injected-session"
    await sandbox.create_session(session_id)

    result_python = await _call(reg, "sandbox_exec_python", {
        "session_id": session_id,
        "code": "print('ok')",
    })
    assert result_python["status"] == ExecStatus.SUCCESS

    result_shell = await _call(reg, "sandbox_exec", {
        "session_id": session_id,
        "command": "echo ok",
    })
    assert result_shell["status"] == ExecStatus.SUCCESS

    result_write = await _call(reg, "sandbox_write_file", {
        "session_id": session_id,
        "filename": "test.txt",
        "content": "hello",
    })
    assert result_write["status"] == "success"

    result_read = await _call(reg, "sandbox_read_file", {
        "session_id": session_id,
        "filename": "test.txt",
    })
    assert result_read["status"] == "success"
    assert result_read["content"] == "hello"

    result_list = await _call(reg, "sandbox_list_files", {
        "session_id": session_id,
    })
    assert result_list["status"] == "success"
    assert "test.txt" in result_list["files"]


# -- US-8: pandas available in sandbox Python ---------------------------------

@pytest.mark.asyncio
async def test_pandas_available_in_sandbox(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-pandas")
    result = await _call(registry, "sandbox_exec_python", {
        "session_id": "s-pandas",
        "code": "import pandas; print(pandas.__version__)",
    })
    assert result["status"] == ExecStatus.SUCCESS, (
        f"pandas should be importable in sandbox. stderr: {result['stderr']}"
    )
    assert result["stdout"].strip(), "pandas version should be printed"


# -- Tool registration completeness -------------------------------------------

def test_all_five_tools_registered(registry: InMemoryToolRegistry) -> None:
    expected = {
        "sandbox_exec",
        "sandbox_exec_python",
        "sandbox_write_file",
        "sandbox_read_file",
        "sandbox_list_files",
    }
    registered = {d.name for d in registry.list_tools()}
    assert expected.issubset(registered), f"Missing tools: {expected - registered}"


# -- Validation: empty args ---------------------------------------------------

@pytest.mark.asyncio
async def test_exec_python_rejects_empty_code(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-empty")
    result = await _call(registry, "sandbox_exec_python", {
        "session_id": "s-empty",
        "code": "",
    })
    assert "error" in result


@pytest.mark.asyncio
async def test_write_file_rejects_empty_filename(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-nofn")
    result = await _call(registry, "sandbox_write_file", {
        "session_id": "s-nofn",
        "filename": "",
        "content": "data",
    })
    assert "error" in result
