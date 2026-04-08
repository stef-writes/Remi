"""Sandbox execution policy — subprocess environment and command screening.

Provides ``build_subprocess_env`` (safe environment for sandbox subprocesses),
``is_dangerous_command`` (shell command blocklist), and
``has_blocked_imports`` (network library import detection).

Used by ``LocalSandbox`` as defense-in-depth.
"""

from __future__ import annotations

import ast
import os
import re
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
    "pip install",
    "pip3 install",
    "uv add",
    "uv pip install",
    "curl ",
    "wget ",
]

# Libraries that must not be importable inside the sandbox.
# Network libraries: the only outbound channel is the injected ``remi``
# bridge module, which uses stdlib ``urllib.request`` against the
# internal REMI API URL.
# Process-spawning libraries: blocked because the exec wrapper neuters
# subprocess/os.system at runtime, and allowing the import would let
# agent code re-import a fresh copy.
BLOCKED_IMPORTS: frozenset[str] = frozenset({
    # Network
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "httplib2",
    "pycurl",
    "grpc",
    "grpcio",
    "websockets",
    "websocket",
    "socket",
    "paramiko",
    "fabric",
    "ftplib",
    "smtplib",
    "imaplib",
    "poplib",
    "telnetlib",
    "xmlrpc",
    # Process spawning
    "subprocess",
    "multiprocessing",
    "pty",
    "ctypes",
})


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


def has_blocked_imports(code: str) -> list[str]:
    """Return network libraries that the code attempts to import.

    Uses AST analysis first (reliable for ``import X`` / ``from X import …``),
    then falls back to a regex scan for dynamic ``__import__("X")`` calls.
    Returns an empty list when no blocked imports are found.
    """
    found: list[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Unparseable code — fall through to regex only.
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in BLOCKED_IMPORTS:
                        found.append(top)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in BLOCKED_IMPORTS:
                        found.append(top)

    # Catch dynamic imports: __import__("httpx"), importlib.import_module("httpx")
    for match in re.finditer(
        r"""(?:__import__|import_module)\s*\(\s*['"]([a-zA-Z_]\w*)['"]""",
        code,
    ):
        mod = match.group(1)
        if mod in BLOCKED_IMPORTS and mod not in found:
            found.append(mod)

    return found
