"""Tests for the analysis tool surface — python and bash.

Every tool is exercised end-to-end through the real LocalSandbox (temp dirs,
real subprocesses). No mocks of the sandbox itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from remi.agent.sandbox.local import LocalSandbox
from remi.agent.sandbox.types import ExecStatus
from remi.agent.tools.registry import InMemoryToolRegistry
from remi.agent.tools.sandbox import AnalysisToolProvider


@pytest.fixture
def sandbox(tmp_path: Path) -> LocalSandbox:
    from remi.application.sdk import __file__ as sdk_path

    sb = LocalSandbox(root=tmp_path / "sandbox")
    sb.set_session_files({"remi.py": Path(sdk_path).read_text("utf-8")})
    return sb


@pytest.fixture
def registry(sandbox: LocalSandbox) -> InMemoryToolRegistry:
    reg = InMemoryToolRegistry()
    AnalysisToolProvider(sandbox).register(reg)
    return reg


async def _call(registry: InMemoryToolRegistry, name: str, args: dict) -> dict:
    entry = registry.get(name)
    assert entry is not None, f"Tool '{name}' not registered"
    fn, _ = entry
    return await fn(args)


# -- python tool ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_python_tool(sandbox: LocalSandbox, registry: InMemoryToolRegistry) -> None:
    await sandbox.create_session("s1")
    result = await _call(
        registry,
        "python",
        {"session_id": "s1", "code": "print(2 + 2)"},
    )
    assert result["status"] == ExecStatus.SUCCESS
    assert "4" in result["stdout"]
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_python_error_returns_stderr(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-err")
    result = await _call(
        registry,
        "python",
        {"session_id": "s-err", "code": "raise ValueError('boom')"},
    )
    assert result["status"] == ExecStatus.ERROR
    assert "boom" in result["stderr"]


@pytest.mark.asyncio
async def test_python_persistent_state(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    """Variables survive between python calls."""
    await sandbox.create_session("persist")
    await _call(registry, "python", {"session_id": "persist", "code": "x = 42"})
    result = await _call(registry, "python", {"session_id": "persist", "code": "print(x + 8)"})
    assert result["status"] == ExecStatus.SUCCESS
    assert "50" in result["stdout"]


# -- bash tool -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_bash_tool(sandbox: LocalSandbox, registry: InMemoryToolRegistry) -> None:
    await sandbox.create_session("s2")
    result = await _call(
        registry,
        "bash",
        {"session_id": "s2", "command": "echo hello"},
    )
    assert result["status"] == ExecStatus.SUCCESS
    assert "hello" in result["stdout"]


# -- file I/O via python -------------------------------------------------------


@pytest.mark.asyncio
async def test_write_and_read_via_python(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s3")
    write_result = await _call(
        registry,
        "python",
        {
            "session_id": "s3",
            "code": 'with open("report.md", "w") as f:\n    f.write("# Report\\n94%")\nprint("done")',
        },
    )
    assert write_result["status"] == ExecStatus.SUCCESS

    read_result = await _call(
        registry,
        "python",
        {
            "session_id": "s3",
            "code": 'print(open("report.md").read())',
        },
    )
    assert "94%" in read_result["stdout"]


# -- list files via bash -------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_via_bash(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s4")
    await _call(
        registry,
        "python",
        {
            "session_id": "s4",
            "code": (
                'with open("a.csv", "w") as f: f.write("x,y")\n'
                'with open("b.json", "w") as f: f.write("{}")'
            ),
        },
    )

    result = await _call(registry, "bash", {"session_id": "s4", "command": "ls"})
    assert result["status"] == ExecStatus.SUCCESS
    assert "a.csv" in result["stdout"]
    assert "b.json" in result["stdout"]


# -- SDK auto-written -----------------------------------------------------------


@pytest.mark.asyncio
async def test_session_has_sdk(sandbox: LocalSandbox) -> None:
    session = await sandbox.create_session("s5")
    sdk_path = Path(session.working_dir) / "remi.py"
    assert sdk_path.exists(), "remi.py should be auto-written on session create"
    source = sdk_path.read_text()
    assert "def properties(" in source
    assert "def rent_roll(" in source
    assert "def managers(" in source


# -- session_id injection -------------------------------------------------------


@pytest.mark.asyncio
async def test_session_id_injection(sandbox: LocalSandbox) -> None:
    reg = InMemoryToolRegistry()
    AnalysisToolProvider(sandbox).register(reg)

    session_id = "injected-session"
    await sandbox.create_session(session_id)

    result_python = await _call(
        reg,
        "python",
        {"session_id": session_id, "code": "print('ok')"},
    )
    assert result_python["status"] == ExecStatus.SUCCESS

    result_bash = await _call(
        reg,
        "bash",
        {"session_id": session_id, "command": "echo ok"},
    )
    assert result_bash["status"] == ExecStatus.SUCCESS


# -- pandas available -----------------------------------------------------------


@pytest.mark.asyncio
async def test_pandas_available_in_sandbox(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-pandas")
    result = await _call(
        registry,
        "python",
        {"session_id": "s-pandas", "code": "import pandas; print(pandas.__version__)"},
    )
    assert result["status"] == ExecStatus.SUCCESS, (
        f"pandas should be importable in sandbox. stderr: {result['stderr']}"
    )
    assert result["stdout"].strip(), "pandas version should be printed"


# -- Tool registration completeness --------------------------------------------


def test_two_tools_registered(registry: InMemoryToolRegistry) -> None:
    expected = {"python", "bash"}
    registered = {d.name for d in registry.list_tools()}
    assert expected.issubset(registered), f"Missing tools: {expected - registered}"


# -- Validation: empty args ----------------------------------------------------


@pytest.mark.asyncio
async def test_python_rejects_empty_code(
    sandbox: LocalSandbox, registry: InMemoryToolRegistry
) -> None:
    await sandbox.create_session("s-empty")
    result = await _call(
        registry,
        "python",
        {"session_id": "s-empty", "code": ""},
    )
    assert "error" in result
