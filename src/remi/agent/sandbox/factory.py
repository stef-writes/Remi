"""Sandbox factory — selects and constructs the sandbox backend.

The container calls ``build_sandbox(settings)`` — it does not inline
backend selection or construction logic.

Supported backends
------------------
local  (default)
    Long-lived Python subprocess per session running on the host.
    Adequate for single-server deployments where the API and agent
    processes share the same machine.

docker
    Spawn an isolated Docker container per session via the Docker socket.
    Requires ``/var/run/docker.sock`` to be mounted into the API container
    and the ``remi-sandbox`` image to be present on the host.
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
    """Construct the sandbox backend selected by ``settings.sandbox.backend``."""
    cfg = settings.sandbox
    api_url = settings.api.resolved_internal_url()
    extra_env = {"REMI_API_URL": api_url}

    backend = cfg.backend.lower()

    if backend == "docker":
        from remi.agent.sandbox.docker import DockerSandbox

        _log.info(
            "sandbox_backend",
            backend="docker",
            api_url=api_url,
            image=cfg.image,
            network=cfg.network,
        )
        sb: Sandbox = DockerSandbox(
            image=cfg.image,
            network=cfg.network,
            extra_env=extra_env,
            default_timeout=cfg.default_timeout,
            max_output_bytes=cfg.max_output_bytes,
            session_ttl_seconds=cfg.session_ttl_seconds,
            memory_limit=cfg.memory_limit,
            cpu_quota=cfg.cpu_quota,
            pids_limit=cfg.pids_limit,
        )
    else:
        if backend != "local":
            _log.warning(
                "sandbox_unknown_backend",
                backend=backend,
                fallback="local",
            )
        _log.info("sandbox_backend", backend="local", api_url=api_url)
        sb = LocalSandbox(
            extra_env=extra_env,
            default_timeout=cfg.default_timeout,
            max_output_bytes=cfg.max_output_bytes,
            session_ttl_seconds=cfg.session_ttl_seconds,
        )

    if session_files:
        sb.set_session_files(session_files)
    return sb
