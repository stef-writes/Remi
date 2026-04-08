"""Docker container sandbox — one container per session with network isolation.

Each session gets a dedicated Docker container running the ``remi-sandbox``
image.  The container stays alive for the session's lifetime (variables
survive between ``exec_python`` calls), and is removed on ``destroy_session``.

Security posture:
- Attached to an internal-only Docker network (no internet egress)
- Read-only root filesystem with tmpfs at /session and /tmp
- Memory, CPU, and PID limits enforced
- Non-root user (uid 1001) inside the container
- No privileged mode, no cap-add, no-new-privileges
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from remi.agent.sandbox.policy import has_blocked_imports, is_dangerous_command
from remi.agent.sandbox.types import ExecResult, ExecStatus, Sandbox, SandboxSession

_log = structlog.get_logger(__name__)

_SENTINEL = "__REMI_EXEC_DONE__"

_STAGING_ROOT = Path(tempfile.gettempdir()) / "remi-sandbox-staging"

_EXEC_WRAPPER = f'''\
import sys, io, traceback

_remi_sentinel = "{_SENTINEL}"

while True:
    _remi_lines: list[str] = []
    for _remi_line in sys.stdin:
        _remi_line = _remi_line.rstrip("\\n")
        if _remi_line == _remi_sentinel:
            break
        _remi_lines.append(_remi_line)
    else:
        break

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


def _import_aiodocker():  # type: ignore[no-untyped-def]
    """Lazy import to avoid hard dependency when backend=local."""
    try:
        import aiodocker
    except ImportError as exc:
        raise RuntimeError(
            "aiodocker is required for the Docker sandbox backend. "
            "Install it with: uv add aiodocker"
        ) from exc
    return aiodocker


class DockerSandbox(Sandbox):
    """Docker container-per-session sandbox with network isolation.

    Each session is a long-lived container running ``sleep infinity``.
    Code execution uses ``docker exec`` to send code to a persistent
    Python interpreter inside the container.  This gives variable
    persistence parity with ``LocalSandbox``.
    """

    def __init__(
        self,
        *,
        image: str = "remi-sandbox:latest",
        network: str = "remi_sandbox",
        extra_env: dict[str, str] | None = None,
        default_timeout: int = 30,
        max_output_bytes: int = 100_000,
        session_ttl_seconds: int = 3600,
        memory_limit: str = "512m",
        cpu_quota: int = 50_000,
        pids_limit: int = 64,
    ) -> None:
        self._image = image
        self._network = network
        self._extra_env = extra_env or {}
        self._default_timeout = default_timeout
        self._max_output = max_output_bytes
        self._session_ttl = session_ttl_seconds
        self._memory_limit = memory_limit
        self._cpu_quota = cpu_quota
        self._pids_limit = pids_limit

        self._sessions: dict[str, SandboxSession] = {}
        self._containers: dict[str, str] = {}  # session_id -> container_id
        self._session_last_used: dict[str, datetime] = {}
        self._session_files: dict[str, str] = {}

        self._client: Any = None

        _STAGING_ROOT.mkdir(parents=True, exist_ok=True)

    async def _get_client(self) -> Any:
        if self._client is None:
            aiodocker = _import_aiodocker()
            self._client = aiodocker.Docker()
        return self._client

    def set_session_files(self, files: dict[str, str]) -> None:
        self._session_files = files

    def _touch(self, session_id: str) -> None:
        self._session_last_used[session_id] = datetime.now(UTC)

    def _staging_dir(self, session_id: str) -> Path:
        return _STAGING_ROOT / session_id

    async def create_session(
        self,
        session_id: str | None = None,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> SandboxSession:
        sid = session_id or f"sandbox-{uuid.uuid4().hex[:12]}"
        client = await self._get_client()

        staging = self._staging_dir(sid)
        staging.mkdir(parents=True, exist_ok=True)
        for name, content in self._session_files.items():
            (staging / name).write_text(content, encoding="utf-8")
        (staging / "_remi_exec_wrapper.py").write_text(
            _EXEC_WRAPPER, encoding="utf-8",
        )

        env = {**self._extra_env, **(extra_env or {})}
        env_list = [f"{k}={v}" for k, v in env.items()]

        container_name = f"remi-sandbox-{sid}"

        config: dict[str, Any] = {
            "Image": self._image,
            "Cmd": ["sleep", "infinity"],
            "Env": env_list,
            "WorkingDir": "/session",
            "User": "1001",
            "HostConfig": {
                "Memory": self._parse_memory(self._memory_limit),
                "CpuQuota": self._cpu_quota,
                "CpuPeriod": 100_000,
                "PidsLimit": self._pids_limit,
                "ReadonlyRootfs": True,
                "SecurityOpt": ["no-new-privileges"],
                "Tmpfs": {
                    "/session": "rw,nosuid,size=256m,uid=1001,gid=1001",
                    "/tmp": "rw,nosuid,size=64m,uid=1001,gid=1001",
                },
                "Binds": [
                    f"{staging}:/opt/init:ro",
                ],
                "NetworkMode": self._network,
            },
        }

        try:
            container = await client.containers.create_or_replace(
                container_name, config,
            )
            await container.start()

            info = await container.show()
            container_id = info["Id"]
            self._containers[sid] = container_id

            await self._docker_exec(
                container_id,
                ["sh", "-c", "cp /opt/init/* /session/ 2>/dev/null; true"],
                timeout=10,
            )

        except Exception:
            _log.error(
                "docker_session_create_failed",
                session_id=sid,
                image=self._image,
                exc_info=True,
            )
            shutil.rmtree(staging, ignore_errors=True)
            raise

        session = SandboxSession(
            session_id=sid,
            working_dir="/session",
        )
        self._sessions[sid] = session
        self._touch(sid)

        _log.info(
            "docker_session_created",
            session_id=sid,
            container=container_id[:12],
            image=self._image,
            network=self._network,
        )
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
            return ExecResult(
                status=ExecStatus.ERROR,
                error=f"Session '{session_id}' not found",
            )

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

        container_id = self._containers[session_id]
        timeout = timeout_seconds or self._default_timeout

        start = time.monotonic()
        try:
            code_b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
            write_cmd = [
                "sh", "-c",
                f"echo '{code_b64}' | base64 -d > /tmp/_remi_code.py",
            ]
            await self._docker_exec(container_id, write_cmd, timeout=10)

            result = await self._docker_exec(
                container_id,
                ["python", "-u", "/tmp/_remi_code.py"],
                timeout=timeout,
            )
        except TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecResult(
                status=ExecStatus.TIMEOUT,
                exit_code=-1,
                duration_ms=elapsed,
                error=f"Timed out after {timeout}s",
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            _log.error(
                "docker_exec_python_error",
                session_id=session_id,
                error=str(exc),
                exc_info=True,
            )
            return ExecResult(
                status=ExecStatus.ERROR,
                exit_code=-1,
                duration_ms=elapsed,
                error=str(exc),
            )

        elapsed = (time.monotonic() - start) * 1000
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", 0)

        self._touch(session_id)
        session.exec_count += 1

        files = await self._list_container_files(container_id)
        new_files = [f for f in files if f not in session.files]
        session.files = files

        return ExecResult(
            status=ExecStatus.SUCCESS if exit_code == 0 else ExecStatus.ERROR,
            stdout=stdout[: self._max_output].strip(),
            stderr=stderr[: self._max_output].strip(),
            exit_code=exit_code,
            duration_ms=elapsed,
            files_created=new_files,
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
            return ExecResult(
                status=ExecStatus.ERROR,
                error=f"Session '{session_id}' not found",
            )

        if is_dangerous_command(command):
            return ExecResult(
                status=ExecStatus.ERROR,
                error=f"Command blocked by sandbox policy: {command[:80]}",
            )

        container_id = self._containers[session_id]
        timeout = timeout_seconds or self._default_timeout

        start = time.monotonic()
        try:
            result = await self._docker_exec(
                container_id,
                ["sh", "-c", command],
                timeout=timeout,
            )
        except TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecResult(
                status=ExecStatus.TIMEOUT,
                exit_code=-1,
                duration_ms=elapsed,
                error=f"Timed out after {timeout}s",
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            _log.error(
                "docker_exec_shell_error",
                session_id=session_id,
                error=str(exc),
                exc_info=True,
            )
            return ExecResult(
                status=ExecStatus.ERROR,
                exit_code=-1,
                duration_ms=elapsed,
                error=str(exc),
            )

        elapsed = (time.monotonic() - start) * 1000
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", 0)

        self._touch(session_id)
        session.exec_count += 1

        files = await self._list_container_files(container_id)
        new_files = [f for f in files if f not in session.files]
        session.files = files

        return ExecResult(
            status=ExecStatus.SUCCESS if exit_code == 0 else ExecStatus.ERROR,
            stdout=stdout[: self._max_output].strip(),
            stderr=stderr[: self._max_output].strip(),
            exit_code=exit_code,
            duration_ms=elapsed,
            files_created=new_files,
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

        container_id = self._containers[session_id]
        safe_name = Path(filename).name

        content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        await self._docker_exec(
            container_id,
            ["sh", "-c", f"echo '{content_b64}' | base64 -d > /session/{safe_name}"],
            timeout=10,
        )

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

        container_id = self._containers[session_id]
        safe_name = Path(filename).name

        try:
            result = await self._docker_exec(
                container_id,
                ["cat", f"/session/{safe_name}"],
                timeout=10,
            )
            return result.get("stdout", "")
        except Exception:
            return None

    async def list_files(self, session_id: str) -> list[str]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        container_id = self._containers.get(session_id)
        if container_id is None:
            return []
        return await self._list_container_files(container_id)

    async def get_session(self, session_id: str) -> SandboxSession | None:
        return self._sessions.get(session_id)

    async def destroy_session(self, session_id: str) -> None:
        container_id = self._containers.pop(session_id, None)
        if container_id is not None:
            try:
                client = await self._get_client()
                container = client.containers.container(container_id)
                await container.kill()
                await container.delete(force=True)
            except Exception:
                _log.warning(
                    "docker_container_cleanup_error",
                    session_id=session_id,
                    container=container_id[:12] if container_id else "?",
                    exc_info=True,
                )

        self._sessions.pop(session_id, None)
        self._session_last_used.pop(session_id, None)

        staging = self._staging_dir(session_id)
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

        _log.info("docker_session_destroyed", session_id=session_id)

    async def reap_expired_sessions(self) -> int:
        if not self._session_ttl:
            return 0

        now = datetime.now(UTC)
        expired = [
            sid
            for sid, last_used in list(self._session_last_used.items())
            if (now - last_used).total_seconds() > self._session_ttl
        ]

        for sid in expired:
            _log.info("docker_session_ttl_expired", session_id=sid)
            await self.destroy_session(sid)

        return len(expired)

    async def close(self) -> None:
        """Shut down all sessions and release the Docker client."""
        for sid in list(self._sessions):
            await self.destroy_session(sid)
        if self._client is not None:
            await self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _docker_exec(
        self,
        container_id: str,
        cmd: list[str],
        *,
        timeout: int = 30,
        detach: bool = False,
    ) -> dict[str, Any]:
        """Run a command inside a container via ``docker exec``."""
        client = await self._get_client()
        container = client.containers.container(container_id)

        exec_obj = await container.exec(
            cmd=cmd,
            stdout=True,
            stderr=True,
            tty=False,
            workdir="/session",
        )

        if detach:
            await exec_obj.start(detach=True)
            return {"stdout": "", "stderr": "", "exit_code": 0}

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        async def _collect() -> None:
            stream = exec_obj.start(detach=False)
            async with stream as s:
                while True:
                    msg = await s.read_out()
                    if msg is None:
                        break
                    text = msg.data.decode("utf-8", errors="replace")
                    if msg.stream == 1:
                        stdout_parts.append(text)
                    elif msg.stream == 2:
                        stderr_parts.append(text)

        try:
            await asyncio.wait_for(_collect(), timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f"docker exec timed out after {timeout}s") from None

        inspect = await exec_obj.inspect()
        exit_code = inspect.get("ExitCode", 0)

        return {
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "exit_code": exit_code,
        }

    def _parse_exec_output(self, result: dict[str, Any]) -> tuple[str, str, int]:
        """Parse sentinel-delimited output from the persistent interpreter."""
        raw_stdout = result.get("stdout", "")
        raw_stderr = result.get("stderr", "")

        stdout = ""
        stderr = ""
        exit_code = result.get("exit_code", 0)

        if _SENTINEL in raw_stdout:
            parts = raw_stdout.split(_SENTINEL, 1)
            stdout = parts[0]
        else:
            stdout = raw_stdout

        if _SENTINEL in raw_stderr:
            parts = raw_stderr.split(_SENTINEL)
            stderr = parts[0] if parts else ""
            if len(parts) >= 3:
                rc_text = parts[2].strip() if len(parts) > 2 else ""
                if rc_text.isdigit() or rc_text.lstrip("-").isdigit():
                    exit_code = int(rc_text)
        else:
            stderr = raw_stderr

        return stdout, stderr, exit_code

    async def _list_container_files(self, container_id: str) -> list[str]:
        """List user files in /session/ inside the container."""
        try:
            result = await self._docker_exec(
                container_id,
                [
                    "sh", "-c",
                    "ls -1 /session/ 2>/dev/null | "
                    "grep -v '^_remi_' | grep -v '^init$'",
                ],
                timeout=5,
            )
            stdout = result.get("stdout", "").strip()
            if not stdout:
                return []
            return sorted(stdout.split("\n"))
        except Exception:
            return []

    @staticmethod
    def _parse_memory(limit: str) -> int:
        """Convert human memory string (e.g. '512m') to bytes."""
        limit = limit.strip().lower()
        if limit.endswith("g"):
            return int(float(limit[:-1]) * 1024 * 1024 * 1024)
        if limit.endswith("m"):
            return int(float(limit[:-1]) * 1024 * 1024)
        if limit.endswith("k"):
            return int(float(limit[:-1]) * 1024)
        return int(limit)
