"""HTTP request tool — read-only access to the REMI API surface.

Constrained to GET requests against the local REMI API. Mutations
(POST, PATCH, DELETE) are blocked — agents perform writes through
dedicated workflow tools or the sandbox SDK, both of which have
explicit, auditable contracts.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import structlog

from remi.agent.types import ToolArg, ToolDefinition, ToolProvider, ToolRegistry

logger = structlog.get_logger("remi.agent.tools.http")

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0"}


class HttpToolProvider(ToolProvider):
    def __init__(
        self,
        *,
        api_base_url: str = "http://127.0.0.1:8000",
        api_path_examples: str = "",
    ) -> None:
        self._base = api_base_url.rstrip("/")
        self._api_path_examples = api_path_examples

    def register(self, registry: ToolRegistry) -> None:
        _base = self._base

        async def http_request(args: dict[str, Any]) -> Any:
            method = (args.get("method", "GET")).upper()
            path = args.get("path", "")
            timeout = min(int(args.get("timeout", 30)), 120)

            if method != "GET":
                return {
                    "error": (
                        f"http_request is read-only (GET). "
                        f"Use the remi SDK in Python for mutations "
                        f"(remi.create_action, remi.create_note)."
                    ),
                }

            if not path:
                return {"error": "path is required"}

            if not path.startswith("/"):
                path = f"/{path}"

            url = f"{_base}{path}"

            parsed = urlparse(url)
            if parsed.hostname not in _ALLOWED_HOSTS:
                return {
                    "error": f"Requests to {parsed.hostname} are not allowed. "
                    f"Only local REMI API requests are permitted.",
                }

            import aiohttp

            try:
                async with aiohttp.ClientSession() as session:
                    kwargs: dict[str, Any] = {
                        "timeout": aiohttp.ClientTimeout(total=timeout),
                        "headers": {"Accept": "application/json"},
                    }

                    async with session.get(url, **kwargs) as resp:
                        status = resp.status
                        try:
                            response_body = await resp.json()
                        except Exception:
                            response_body = await resp.text()

                        return {
                            "status": status,
                            "body": response_body,
                            "url": url,
                            "method": method,
                        }

            except Exception as exc:
                logger.error(
                    "http_request_error",
                    url=url,
                    method=method,
                    error=str(exc),
                    exc_info=True,
                )
                return {"error": str(exc), "url": url, "method": method}

        base_desc = (
            "Read data from the REMI API (GET only). Use for endpoints "
            "not covered by other tools. For mutations, use the remi SDK "
            "in Python (remi.create_action, remi.create_note).\n\n"
            "Base URL is auto-configured. Pass only the path."
        )
        if self._api_path_examples:
            base_desc = f"{base_desc}\n\n{self._api_path_examples}"

        registry.register(
            "http_request",
            http_request,
            ToolDefinition(
                name="http_request",
                description=base_desc,
                args=[
                    ToolArg(
                        name="path",
                        description="API path (e.g. /api/v1/managers). Base URL is automatic.",
                        required=True,
                    ),
                    ToolArg(
                        name="timeout",
                        description="Timeout in seconds (default 30, max 120)",
                    ),
                ],
            ),
        )
