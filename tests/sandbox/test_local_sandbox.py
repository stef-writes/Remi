"""Test LocalSandbox — isolated subprocess execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from remi.agent.sandbox.local import LocalSandbox
from remi.agent.sandbox.types import ExecStatus


@pytest.fixture
def sandbox(tmp_path: Path) -> LocalSandbox:
    return LocalSandbox(root=tmp_path / "sandbox")


@pytest.mark.asyncio
async def test_create_session(sandbox: LocalSandbox) -> None:
    session = await sandbox.create_session("test-1")
    assert session.session_id == "test-1"
    assert Path(session.working_dir).exists()


@pytest.mark.asyncio
async def test_exec_python_hello(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s1")
    result = await sandbox.exec_python("s1", 'print("hello from sandbox")')
    assert result.status == ExecStatus.SUCCESS
    assert "hello from sandbox" in result.stdout
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_exec_python_error(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s2")
    result = await sandbox.exec_python("s2", "raise ValueError('boom')")
    assert result.status == ExecStatus.ERROR
    assert result.exit_code != 0
    assert "boom" in result.stderr


@pytest.mark.asyncio
async def test_exec_python_timeout(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s3")
    result = await sandbox.exec_python(
        "s3",
        "import time; time.sleep(10)",
        timeout_seconds=1,
    )
    assert result.status == ExecStatus.TIMEOUT
    assert result.error is not None
    assert "Timed out" in result.error


@pytest.mark.asyncio
async def test_write_and_read_file(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s4")
    name = await sandbox.write_file("s4", "data.csv", "a,b,c\n1,2,3\n")
    assert name == "data.csv"

    content = await sandbox.read_file("s4", "data.csv")
    assert content is not None
    assert "a,b,c" in content


@pytest.mark.asyncio
async def test_exec_python_reads_written_file(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s5")
    await sandbox.write_file("s5", "input.txt", "hello world")

    result = await sandbox.exec_python(
        "s5",
        """
with open("input.txt") as f:
    print(f.read().upper())
""",
    )
    assert result.status == ExecStatus.SUCCESS
    assert "HELLO WORLD" in result.stdout


@pytest.mark.asyncio
async def test_exec_python_creates_file(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s6")
    result = await sandbox.exec_python(
        "s6",
        """
with open("output.txt", "w") as f:
    f.write("result: 42")
print("done")
""",
    )
    assert result.status == ExecStatus.SUCCESS
    assert "output.txt" in result.files_created

    content = await sandbox.read_file("s6", "output.txt")
    assert content == "result: 42"


@pytest.mark.asyncio
async def test_list_files(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s7")
    await sandbox.write_file("s7", "a.txt", "aaa")
    await sandbox.write_file("s7", "b.txt", "bbb")

    files = await sandbox.list_files("s7")
    assert "a.txt" in files
    assert "b.txt" in files


@pytest.mark.asyncio
async def test_destroy_session(sandbox: LocalSandbox) -> None:
    session = await sandbox.create_session("s8")
    work_dir = Path(session.working_dir)
    assert work_dir.exists()

    await sandbox.destroy_session("s8")
    assert not work_dir.exists()
    assert await sandbox.get_session("s8") is None


@pytest.mark.asyncio
async def test_exec_shell_blocked(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s9")
    result = await sandbox.exec_shell("s9", "sudo rm -rf /")
    assert result.status == ExecStatus.ERROR
    assert "blocked" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_exec_shell_allowed(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s10")
    result = await sandbox.exec_shell("s10", "echo hello")
    assert result.status == ExecStatus.SUCCESS
    assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_session_not_found(sandbox: LocalSandbox) -> None:
    result = await sandbox.exec_python("nonexistent", "print(1)")
    assert result.status == ExecStatus.ERROR
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_path_traversal_blocked(sandbox: LocalSandbox) -> None:
    await sandbox.create_session("s11")
    name = await sandbox.write_file("s11", "../../etc/passwd", "hacked")
    assert name == "passwd"


@pytest.mark.asyncio
async def test_persistent_python_state(sandbox: LocalSandbox) -> None:
    """Variables survive between exec_python calls in the same session."""
    await sandbox.create_session("persist")

    r1 = await sandbox.exec_python("persist", "x = 42")
    assert r1.status == ExecStatus.SUCCESS

    r2 = await sandbox.exec_python("persist", "print(x + 8)")
    assert r2.status == ExecStatus.SUCCESS
    assert "50" in r2.stdout


@pytest.mark.asyncio
async def test_persistent_import_survives(sandbox: LocalSandbox) -> None:
    """Imports done in one call are available in the next."""
    await sandbox.create_session("imp")

    r1 = await sandbox.exec_python("imp", "import json")
    assert r1.status == ExecStatus.SUCCESS

    r2 = await sandbox.exec_python("imp", 'print(json.dumps({"a": 1}))')
    assert r2.status == ExecStatus.SUCCESS
    assert '{"a": 1}' in r2.stdout


@pytest.mark.asyncio
async def test_interpreter_restarts_after_timeout(sandbox: LocalSandbox) -> None:
    """After a timeout kills the interpreter, the next call still works."""
    await sandbox.create_session("restart")

    r1 = await sandbox.exec_python(
        "restart", "import time; time.sleep(10)", timeout_seconds=1
    )
    assert r1.status == ExecStatus.TIMEOUT

    r2 = await sandbox.exec_python("restart", "print('recovered')")
    assert r2.status == ExecStatus.SUCCESS
    assert "recovered" in r2.stdout


@pytest.mark.asyncio
async def test_bash_persistent_cwd(sandbox: LocalSandbox) -> None:
    """Working directory survives between exec_shell calls."""
    session = await sandbox.create_session("cwd")
    work_dir = session.working_dir

    r1 = await sandbox.exec_shell("cwd", "mkdir -p subdir")
    assert r1.status == ExecStatus.SUCCESS

    r2 = await sandbox.exec_shell("cwd", "cd subdir && pwd")
    assert r2.status == ExecStatus.SUCCESS
    assert r2.stdout.endswith("subdir")

    r3 = await sandbox.exec_shell("cwd", "pwd")
    assert r3.status == ExecStatus.SUCCESS
    assert r3.stdout.endswith("subdir"), f"cwd should persist: got {r3.stdout}"

    r4 = await sandbox.exec_shell("cwd", "cd .. && pwd")
    assert r4.status == ExecStatus.SUCCESS
    assert r4.stdout.rstrip("/") == work_dir.rstrip("/")
