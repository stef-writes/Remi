"""HTTP middleware — request-ID propagation and timing.

Extracts or generates a ``request_id`` for every HTTP request and binds
it to structlog context vars so that every log line emitted during the
request automatically includes the ID.  The ID is echoed back in the
``X-Request-ID`` response header for client-side correlation.

Also logs method, path, status code, and ``duration_ms`` for every
request so you can monitor latency from structured log output.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_HEADER = "X-Request-ID"
_logger = structlog.get_logger("remi.http")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        t0 = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.monotonic() - t0) * 1000)
            path = request.url.path
            if not path.startswith("/ws/"):
                _logger.info(
                    "http_request",
                    method=request.method,
                    path=path,
                    status=status_code,
                    duration_ms=duration_ms,
                )
            structlog.contextvars.unbind_contextvars("request_id")
