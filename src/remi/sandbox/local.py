"""Local subprocess sandbox — isolated execution via temp directories and subprocess.

Each session gets a dedicated temp directory. Shell commands run in a
subprocess with the working directory set to the session dir. The subprocess
inherits a minimal environment with the ``remi`` CLI on PATH.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

from remi.models.sandbox import ExecResult, ExecStatus, Sandbox, SandboxSession
from remi.sandbox.data_bridge import DATA_BRIDGE_SOURCE

_log = structlog.get_logger(__name__)

_SANDBOX_ROOT = Path(tempfile.gettempdir()) / "remi-sandbox"


def _safe_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a restricted environment for sandbox subprocesses.

    Ensures the ``remi`` CLI entrypoint is on PATH even when the venv
    was not formally activated (i.e. ``VIRTUAL_ENV`` is unset but we are
    running from ``.venv/bin/python``).
    """
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
        "HOME": "/tmp",
        "LANG": "en_US.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    venv_path = os.environ.get("VIRTUAL_ENV")
    if venv_path:
        env["VIRTUAL_ENV"] = venv_path
        env["PATH"] = f"{venv_path}/bin:{env['PATH']}"
    else:
        python_bin_dir = str(Path(sys.executable).resolve().parent)
        if python_bin_dir not in env["PATH"].split(os.pathsep):
            env["PATH"] = f"{python_bin_dir}:{env['PATH']}"
    if extra:
        env.update(extra)
    return env


class LocalSandbox(Sandbox):
    """Subprocess-based sandbox using isolated temp directories."""

    def __init__(
        self,
        root: Path | None = None,
        default_timeout: int = 30,
        max_output_bytes: int = 100_000,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self._root = root or _SANDBOX_ROOT
        self._root.mkdir(parents=True, exist_ok=True)
        self._default_timeout = default_timeout
        self._max_output = max_output_bytes
        self._extra_env = extra_env or {}
        self._sessions: dict[str, SandboxSession] = {}
        self._session_env: dict[str, dict[str, str]] = {}

    async def create_session(
        self,
        session_id: str | None = None,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> SandboxSession:
        sid = session_id or f"sandbox-{uuid.uuid4().hex[:12]}"
        work_dir = self._root / sid
        work_dir.mkdir(parents=True, exist_ok=True)

        session = SandboxSession(session_id=sid, working_dir=str(work_dir))
        self._sessions[sid] = session
        if extra_env:
            self._session_env[sid] = extra_env

        (work_dir / "remi_data.py").write_text(DATA_BRIDGE_SOURCE, encoding="utf-8")

        _log.info("sandbox_session_created", session_id=sid, dir=str(work_dir))
        return session

    async def exec_python(
        self,
        session_id: str,
        code: str,
        *,
        timeout_seconds: int = 30,
    ) -> ExecResult:
        session = self._sessions.get(session_id)
        if session is None:
            return ExecResult(status=ExecStatus.ERROR, error=f"Session '{session_id}' not found")

        work_dir = Path(session.working_dir)
        script_path = work_dir / f"_exec_{session.exec_count}.py"
        script_path.write_text(code, encoding="utf-8")

        python_bin = sys.executable
        venv = os.environ.get("VIRTUAL_ENV")
        if venv:
            candidate = Path(venv) / "bin" / "python"
            if candidate.exists():
                python_bin = str(candidate)

        result = await self._run_subprocess(
            [python_bin, str(script_path)],
            cwd=work_dir,
            timeout=timeout_seconds or self._default_timeout,
            session_id=session_id,
        )

        session.exec_count += 1
        new_files = self._scan_files(work_dir)
        result_files = [f for f in new_files if f not in session.files]
        session.files = new_files

        return ExecResult(
            status=result["status"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            duration_ms=result["duration_ms"],
            files_created=result_files,
            error=result.get("error"),
        )

    async def exec_shell(
        self,
        session_id: str,
        command: str,
        *,
        timeout_seconds: int = 30,
    ) -> ExecResult:
        session = self._sessions.get(session_id)
        if session is None:
            return ExecResult(status=ExecStatus.ERROR, error=f"Session '{session_id}' not found")

        work_dir = Path(session.working_dir)

        if _is_dangerous_command(command):
            return ExecResult(
                status=ExecStatus.ERROR,
                error=f"Command blocked by sandbox policy: {command[:80]}",
            )

        result = await self._run_subprocess(
            command,
            cwd=work_dir,
            timeout=timeout_seconds or self._default_timeout,
            shell=True,
            session_id=session_id,
        )

        session.exec_count += 1
        new_files = self._scan_files(work_dir)
        result_files = [f for f in new_files if f not in session.files]
        session.files = new_files

        return ExecResult(
            status=result["status"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            exit_code=result["exit_code"],
            duration_ms=result["duration_ms"],
            files_created=result_files,
            error=result.get("error"),
        )

    async def write_file(
        self,
        session_id: str,
        filename: str,
        content: str,
    ) -> str:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found")

        work_dir = Path(session.working_dir)
        safe_name = Path(filename).name
        file_path = work_dir / safe_name
        file_path.write_text(content, encoding="utf-8")

        if safe_name not in session.files:
            session.files.append(safe_name)

        return safe_name

    async def read_file(
        self,
        session_id: str,
        filename: str,
    ) -> str | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None

        work_dir = Path(session.working_dir)
        safe_name = Path(filename).name
        file_path = work_dir / safe_name

        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    async def list_files(self, session_id: str) -> list[str]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return self._scan_files(Path(session.working_dir))

    async def get_session(self, session_id: str) -> SandboxSession | None:
        return self._sessions.get(session_id)

    async def destroy_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        self._session_env.pop(session_id, None)
        if session is not None:
            work_dir = Path(session.working_dir)
            if work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)
            _log.info("sandbox_session_destroyed", session_id=session_id)

    async def _run_subprocess(
        self,
        cmd: str | list[str],
        cwd: Path,
        timeout: int,
        shell: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        merged = dict(self._extra_env)
        if session_id and session_id in self._session_env:
            merged.update(self._session_env[session_id])
        env = _safe_env(merged)
        start = time.monotonic()

        try:
            if shell:
                proc = await asyncio.create_subprocess_shell(
                    cmd,  # type: ignore[arg-type]
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd),
                    env=env,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd),
                    env=env,
                )

            try:
                stdout_raw, stderr_raw = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed = (time.monotonic() - start) * 1000
                return {
                    "status": ExecStatus.TIMEOUT,
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                    "duration_ms": elapsed,
                    "error": f"Timed out after {timeout}s",
                }

            elapsed = (time.monotonic() - start) * 1000
            stdout = stdout_raw.decode("utf-8", errors="replace")[: self._max_output]
            stderr = stderr_raw.decode("utf-8", errors="replace")[: self._max_output]

            return {
                "status": ExecStatus.SUCCESS if proc.returncode == 0 else ExecStatus.ERROR,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "exit_code": proc.returncode or 0,
                "duration_ms": elapsed,
            }

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return {
                "status": ExecStatus.ERROR,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "duration_ms": elapsed,
                "error": str(exc),
            }

    def _scan_files(self, work_dir: Path) -> list[str]:
        if not work_dir.exists():
            return []
        return sorted(
            f.name for f in work_dir.iterdir() if f.is_file() and not f.name.startswith("_exec_")
        )


def _is_dangerous_command(cmd: str) -> bool:
    """Block commands that could escape the sandbox."""
    blocked = [
        "rm -rf /",
        "rm -rf ~",
        "sudo",
        "chmod 777",
        "curl",
        "wget",
        "nc ",
        "netcat",
        "ssh ",
        "scp ",
        "rsync ",
        "mount ",
        "kill ",
        "pkill ",
        "killall ",
    ]
    cmd_lower = cmd.lower().strip()
    return any(b in cmd_lower for b in blocked)
