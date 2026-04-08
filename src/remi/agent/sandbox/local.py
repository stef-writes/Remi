"""Local subprocess sandbox — isolated execution via temp directories.

Each session gets a dedicated temp directory.  Python code runs in a
**persistent interpreter** (variables survive between calls).  Shell
commands run in one-shot subprocesses.

TTL reaping
-----------
Sessions idle longer than ``session_ttl_seconds`` are automatically
destroyed by ``reap_expired_sessions()``, which the server lifespan
calls on a background timer.  Set ``session_ttl_seconds=0`` to disable
TTL-based cleanup (sessions are only reclaimed by explicit
``destroy_session`` calls).
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from remi.agent.sandbox.policy import (
    build_subprocess_env,
    has_blocked_imports,
    is_dangerous_command,
    resolve_python_bin,
)
from remi.agent.sandbox.types import ExecResult, ExecStatus, Sandbox, SandboxSession

_log = structlog.get_logger(__name__)

_SANDBOX_ROOT = Path(tempfile.gettempdir()) / "remi-sandbox"

_SENTINEL = "__REMI_EXEC_DONE__"

_EXEC_WRAPPER = f'''\
import sys, io, os, traceback
from pathlib import PurePosixPath as _PurePath

# ── Sandbox hardening preamble ──────────────────────────────────────
# Runs once at interpreter startup. Restricts filesystem access to the
# session working directory and /tmp, and removes dangerous os/subprocess
# functions. Bypassable via ctypes — defense-in-depth, not a security
# boundary. The Docker backend is the real wall.

_remi_allowed_roots = set()

def _remi_init_sandbox():
    _cwd = os.getcwd()
    _remi_allowed_roots.add(os.path.realpath(_cwd))
    _remi_allowed_roots.add("/tmp")
    _remi_allowed_roots.add(os.path.realpath("/tmp"))

    _original_open = open

    def _restricted_open(file, mode="r", *args, **kwargs):
        path_str = str(file)
        if not path_str.startswith(("<", "http")):
            real = os.path.realpath(path_str)
            if not any(real.startswith(root) for root in _remi_allowed_roots):
                raise PermissionError(
                    f"Sandbox: access denied to '{{path_str}}'. "
                    f"Files must be in the session directory or /tmp."
                )
        return _original_open(file, mode, *args, **kwargs)

    import builtins
    builtins.open = _restricted_open

    for attr in ("system", "popen", "execl", "execle", "execlp",
                 "execlpe", "execv", "execve", "execvp", "execvpe",
                 "spawnl", "spawnle", "spawnlp", "spawnlpe",
                 "spawnv", "spawnve", "spawnvp", "spawnvpe"):
        if hasattr(os, attr):
            delattr(os, attr)

    try:
        import subprocess as _sp
        for attr in ("run", "call", "check_call", "check_output",
                     "Popen", "getoutput", "getstatusoutput"):
            if hasattr(_sp, attr):
                delattr(_sp, attr)
    except ImportError:
        pass

_remi_init_sandbox()
del _remi_init_sandbox

# ── Execution loop ──────────────────────────────────────────────────

_remi_sentinel = "{_SENTINEL}"

while True:
    _remi_lines: list[str] = []
    for _remi_line in sys.stdin:
        _remi_line = _remi_line.rstrip("\\n")
        if _remi_line == _remi_sentinel:
            break
        _remi_lines.append(_remi_line)
    else:
        break  # EOF — stdin closed

    _remi_code = "\\n".join(_remi_lines)
    _remi_old_stdout = sys.stdout
    _remi_old_stderr = sys.stderr
    _remi_cap_out = io.StringIO()
    _remi_cap_err = io.StringIO()
    sys.stdout = _remi_cap_out
    sys.stderr = _remi_cap_err
    _remi_rc = 0
    try:
        exec(compile(_remi_code, "<sandbox>", "exec"), globals())
    except SystemExit as _remi_e:
        _remi_rc = _remi_e.code if isinstance(_remi_e.code, int) else 1
    except Exception:
        traceback.print_exc(file=_remi_cap_err)
        _remi_rc = 1
    finally:
        sys.stdout = _remi_old_stdout
        sys.stderr = _remi_old_stderr

    _remi_out_text = _remi_cap_out.getvalue()
    _remi_err_text = _remi_cap_err.getvalue()
    print(_remi_out_text, end="", flush=True)
    print(_remi_sentinel, flush=True)
    print(_remi_err_text, end="", file=sys.stderr, flush=True)
    print(_remi_sentinel, file=sys.stderr, flush=True)
    print(str(_remi_rc), file=sys.stderr, flush=True)
'''


class _PersistentInterpreter:
    """A long-lived Python subprocess that accepts code blocks via stdin.

    Code is delimited by a sentinel line.  Stdout and stderr are captured
    per-block using the same sentinel.  Variables and imports survive
    between calls because everything runs in a single ``exec()`` namespace.
    """

    def __init__(self, work_dir: Path, env: dict[str, str], max_output: int) -> None:
        self._work_dir = work_dir
        self._env = env
        self._max_output = max_output
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        wrapper_path = self._work_dir / "_remi_exec_wrapper.py"
        wrapper_path.write_text(_EXEC_WRAPPER, encoding="utf-8")

        self._proc = await asyncio.create_subprocess_exec(
            resolve_python_bin(),
            "-u",
            str(wrapper_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._work_dir),
            env=self._env,
        )

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def execute(self, code: str, timeout: int = 60) -> dict[str, Any]:
        if not self.alive:
            await self.start()
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        assert self._proc.stderr is not None

        payload = code + "\n" + _SENTINEL + "\n"
        self._proc.stdin.write(payload.encode("utf-8"))
        await self._proc.stdin.drain()

        start = time.monotonic()
        try:
            stdout_text = await asyncio.wait_for(
                self._read_until_sentinel(self._proc.stdout),
                timeout=timeout,
            )
            stderr_text = await asyncio.wait_for(
                self._read_until_sentinel(self._proc.stderr),
                timeout=max(timeout - (time.monotonic() - start), 2),
            )
            rc_line = await asyncio.wait_for(
                self._proc.stderr.readline(),
                timeout=2,
            )
        except (TimeoutError, asyncio.TimeoutError):
            elapsed = (time.monotonic() - start) * 1000
            await self.kill()
            return {
                "status": ExecStatus.TIMEOUT,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "duration_ms": elapsed,
                "error": f"Timed out after {timeout}s",
            }

        elapsed = (time.monotonic() - start) * 1000
        exit_code = int(rc_line.decode("utf-8", errors="replace").strip() or "0")

        return {
            "status": ExecStatus.SUCCESS if exit_code == 0 else ExecStatus.ERROR,
            "stdout": stdout_text[: self._max_output].strip(),
            "stderr": stderr_text[: self._max_output].strip(),
            "exit_code": exit_code,
            "duration_ms": elapsed,
        }

    async def _read_until_sentinel(self, stream: asyncio.StreamReader) -> str:
        lines: list[str] = []
        sentinel_bytes = _SENTINEL.encode("utf-8")
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.rstrip(b"\n").rstrip(b"\r")
            if line == sentinel_bytes:
                break
            lines.append(line.decode("utf-8", errors="replace"))
        return "\n".join(lines)

    async def kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
                await self._proc.wait()
            except ProcessLookupError:
                pass
            self._proc = None


class LocalSandbox(Sandbox):
    """Subprocess-based sandbox using isolated temp directories.

    Python code executes in a **persistent interpreter** per session —
    variables and imports survive between ``exec_python`` calls.  Shell
    commands run in one-shot subprocesses.

    Sessions idle longer than ``session_ttl_seconds`` are reclaimed by
    ``reap_expired_sessions()``.  Set to ``0`` to disable TTL cleanup.
    """

    def __init__(
        self,
        root: Path | None = None,
        default_timeout: int = 30,
        max_output_bytes: int = 100_000,
        extra_env: dict[str, str] | None = None,
        session_ttl_seconds: int = 3600,
    ) -> None:
        self._root = root or _SANDBOX_ROOT
        self._root.mkdir(parents=True, exist_ok=True)
        self._default_timeout = default_timeout
        self._max_output = max_output_bytes
        self._extra_env = extra_env or {}
        self._session_ttl = session_ttl_seconds
        self._sessions: dict[str, SandboxSession] = {}
        self._session_env: dict[str, dict[str, str]] = {}
        self._session_last_used: dict[str, datetime] = {}
        self._interpreters: dict[str, _PersistentInterpreter] = {}
        self._session_files: dict[str, str] = {}
        self._session_cwd: dict[str, Path] = {}

    def set_session_files(self, files: dict[str, str]) -> None:
        """Set files to write into every new session's working directory."""
        self._session_files = files

    def _write_session_files(self, work_dir: Path) -> None:
        for name, content in self._session_files.items():
            (work_dir / name).write_text(content, encoding="utf-8")

    def _touch(self, session_id: str) -> None:
        """Record that a session was used right now (for TTL tracking)."""
        self._session_last_used[session_id] = datetime.now(UTC)

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

        self._touch(sid)
        self._write_session_files(work_dir)

        _log.info("sandbox_session_created", session_id=sid, dir=str(work_dir))
        return session

    async def reap_expired_sessions(self) -> int:
        """Destroy sessions that have been idle longer than ``session_ttl_seconds``.

        Returns the number of sessions reaped.  Skips cleanup when TTL is
        disabled (``session_ttl_seconds == 0``).
        """
        if not self._session_ttl:
            return 0

        now = datetime.now(UTC)
        expired = [
            sid
            for sid, last_used in list(self._session_last_used.items())
            if (now - last_used).total_seconds() > self._session_ttl
        ]

        for sid in expired:
            _log.info("sandbox_session_ttl_expired", session_id=sid)
            await self.destroy_session(sid)

        return len(expired)

    def _build_env(self, session_id: str) -> dict[str, str]:
        merged = dict(self._extra_env)
        if session_id in self._session_env:
            merged.update(self._session_env[session_id])
        return build_subprocess_env(merged)

    def _get_interpreter(self, session_id: str) -> _PersistentInterpreter:
        interp = self._interpreters.get(session_id)
        if interp is None or not interp.alive:
            session = self._sessions[session_id]
            work_dir = Path(session.working_dir)
            env = self._build_env(session_id)
            interp = _PersistentInterpreter(work_dir, env, self._max_output)
            self._interpreters[session_id] = interp
        return interp

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

        blocked = has_blocked_imports(code)
        if blocked:
            names = ", ".join(sorted(set(blocked)))
            return ExecResult(
                status=ExecStatus.ERROR,
                error=(
                    f"Blocked network import(s): {names}. "
                    "Use `import remi` to access platform data."
                ),
            )

        work_dir = Path(session.working_dir)
        interp = self._get_interpreter(session_id)

        result = await interp.execute(code, timeout=timeout_seconds or self._default_timeout)

        self._touch(session_id)
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

        if is_dangerous_command(command):
            return ExecResult(
                status=ExecStatus.ERROR,
                error=f"Command blocked by sandbox policy: {command[:80]}",
            )

        cwd = self._session_cwd.get(session_id, work_dir)

        cwd_sentinel = "__REMI_CWD__"
        wrapped = f'{command}\n_remi_ec=$?\necho "{cwd_sentinel}$(pwd)"\nexit $_remi_ec'

        result = await self._run_subprocess(
            wrapped,
            cwd=cwd,
            timeout=timeout_seconds or self._default_timeout,
            shell=True,
            session_id=session_id,
        )

        stdout = result.get("stdout", "")
        if cwd_sentinel in stdout:
            lines = stdout.rsplit(cwd_sentinel, 1)
            result["stdout"] = lines[0].strip()
            new_cwd = lines[1].strip()
            if new_cwd:
                self._session_cwd[session_id] = Path(new_cwd)

        self._touch(session_id)
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
        interp = self._interpreters.pop(session_id, None)
        if interp is not None:
            await interp.kill()

        session = self._sessions.pop(session_id, None)
        self._session_env.pop(session_id, None)
        self._session_cwd.pop(session_id, None)
        self._session_last_used.pop(session_id, None)
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
        env = self._build_env(session_id or "")
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
            f.name
            for f in work_dir.iterdir()
            if f.is_file() and not f.name.startswith("_remi_") and not f.name.startswith("_exec_")
        )
