"""HTTP request tool — gives agents access to the full REMI API surface.

Constrained to the local REMI API by default. Enables agents to hit
any endpoint including mutations (POST actions, notes, signal inference),
not just the read-only subset exposed by remi_data.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import structlog

from remi.agent.types import ToolArg, ToolDefinition, ToolRegistry

logger = structlog.get_logger("remi.application.tools.http")

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0"}


def register_http_tools(
    registry: ToolRegistry,
    *,
    api_base_url: str = "http://127.0.0.1:8000",
    api_path_examples: str = "",
) -> None:
    """Register the ``http_request`` tool.

    Requests are restricted to the REMI API base URL by default.
    """
    _base = api_base_url.rstrip("/")

    async def http_request(args: dict[str, Any]) -> Any:
        method = (args.get("method", "GET")).upper()
        path = args.get("path", "")
        body = args.get("body")
        timeout = min(int(args.get("timeout", 30)), 120)

        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            return {"error": f"Unsupported method: {method}"}

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
                if body is not None and method in ("POST", "PUT", "PATCH"):
                    if isinstance(body, str):
                        try:
                            body = json.loads(body)
                        except json.JSONDecodeError:
                            logger.warning("http_body_not_valid_json", body_preview=body[:200])
                    kwargs["json"] = body
                    kwargs["headers"]["Content-Type"] = "application/json"

                async with session.request(method, url, **kwargs) as resp:
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
                "http_request_error", url=url, method=method,
                error=str(exc), exc_info=True,
            )
            return {"error": str(exc), "url": url, "method": method}

    base_desc = (
        "Make an HTTP request to the API. Use for any operation "
        "not covered by other tools.\n\n"
        "Base URL is auto-configured. Pass only the path."
    )
    if api_path_examples:
        base_desc = f"{base_desc}\n\n{api_path_examples}"

    registry.register(
        "http_request",
        http_request,
        ToolDefinition(
            name="http_request",
            description=base_desc,
            args=[
                ToolArg(
                    name="method",
                    description="HTTP method: GET, POST, PUT, PATCH, DELETE",
                    required=True,
                ),
                ToolArg(
                    name="path",
                    description="API path (e.g. /api/v1/managers). Base URL is automatic.",
                    required=True,
                ),
                ToolArg(
                    name="body",
                    description="Request body as JSON (for POST/PUT/PATCH)",
                ),
                ToolArg(
                    name="timeout",
                    description="Timeout in seconds (default 30, max 120)",
                ),
            ],
        ),
    )
