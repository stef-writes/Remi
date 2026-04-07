"""Sandbox factory — constructs the local sandbox backend.

The container calls ``build_sandbox(settings)`` — it does not inline
backend selection or construction logic.
"""

from __future__ import annotations

import structlog

from remi.agent.sandbox.local import LocalSandbox
from remi.agent.sandbox.types import Sandbox
from remi.types.config import RemiSettings

_log = structlog.get_logger(__name__)


def build_sandbox(
    settings: RemiSettings,
    *,
    session_files: dict[str, str] | None = None,
) -> Sandbox:
    """Construct the sandbox backend."""
    cfg = settings.sandbox
    api_url = f"http://127.0.0.1:{settings.api.port}"
    extra_env = {"REMI_API_URL": api_url}

    _log.info("sandbox_backend", backend="local")
    sb = LocalSandbox(
        extra_env=extra_env,
        default_timeout=cfg.default_timeout,
        max_output_bytes=cfg.max_output_bytes,
    )
    if session_files:
        sb.set_session_files(session_files)
    return sb
