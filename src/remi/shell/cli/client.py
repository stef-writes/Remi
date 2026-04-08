"""HTTP client mode for CLI commands.

When ``REMI_API_URL`` is set, CLI commands proxy to the running API server
instead of bootstrapping a local ``Container``. This is how the agent's
sandbox executes ``remi`` commands — fast, no cold start.

The client returns raw dicts from the API. The CLI command wraps them in
the standard envelope via ``output.py``.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_TIMEOUT = 30


def get_api_url() -> str | None:
    """Return the API URL if client mode is active, else None."""
    return os.environ.get("REMI_API_URL")


def get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET request to the running REMI API."""
    url = _url(path, params)
    req = Request(url)
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {body}") from e
    except URLError as exc:
        raise ConnectionError(
            f"Cannot reach REMI API at {url}"
        ) from exc


def post(path: str, body: dict[str, Any] | None = None) -> Any:
    """POST request to the running REMI API."""
    url = _url(path)
    data = json.dumps(body or {}).encode()
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {body_text}") from e
    except URLError as exc:
        raise ConnectionError(
            f"Cannot reach REMI API at {url}"
        ) from exc


def _url(path: str, params: dict[str, Any] | None = None) -> str:
    base_url = os.environ.get("REMI_API_URL", "http://127.0.0.1:8000")
    prefix = "/api/v1"
    full = f"{base_url}{prefix}{path}"
    if params:
        filtered = {k: v for k, v in params.items() if v is not None}
        if filtered:
            return f"{full}?{urlencode(filtered, doseq=True)}"
    return full
