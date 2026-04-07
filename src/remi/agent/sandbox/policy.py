"""Sandbox execution policy — subprocess environment and command screening.

Provides ``build_subprocess_env`` (safe environment for sandbox subprocesses)
and ``is_dangerous_command`` (shell command blocklist).  Used by
``LocalSandbox`` as defense-in-depth.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf ~",
    "sudo",
    "chmod 777",
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


def build_subprocess_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a restricted environment for sandbox subprocesses.

    Ensures the Python binary (and its venv) is on PATH even when the
    venv was not formally activated (e.g. ``uv run`` sets ``sys.executable``
    inside ``.venv`` but does not export ``VIRTUAL_ENV``).
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
        # Detect venv from sys.executable (covers uv run which doesn't set VIRTUAL_ENV)
        resolved = Path(sys.executable).resolve()
        venv_candidate = resolved.parents[1]
        if (venv_candidate / "pyvenv.cfg").exists():
            env["VIRTUAL_ENV"] = str(venv_candidate)
            env["PATH"] = f"{venv_candidate}/bin:{env['PATH']}"
        else:
            python_bin_dir = str(resolved.parent)
            if python_bin_dir not in env["PATH"].split(os.pathsep):
                env["PATH"] = f"{python_bin_dir}:{env['PATH']}"

    if extra:
        env.update(extra)
    return env


def resolve_python_bin() -> str:
    """Return the path to the Python binary for sandbox subprocesses.

    Prefers the venv's python if detectable, otherwise falls back to
    ``sys.executable``.
    """
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidate = Path(venv) / "bin" / "python"
        if candidate.exists():
            return str(candidate)

    resolved = Path(sys.executable).resolve()
    venv_candidate = resolved.parents[1]
    if (venv_candidate / "pyvenv.cfg").exists():
        candidate = venv_candidate / "bin" / "python"
        if candidate.exists():
            return str(candidate)

    return sys.executable


def is_dangerous_command(cmd: str) -> bool:
    """Block shell commands that could escape the sandbox."""
    cmd_lower = cmd.lower().strip()
    return any(b in cmd_lower for b in _BLOCKED_COMMANDS)
