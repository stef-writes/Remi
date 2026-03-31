"""Thin HTTP client for CLI commands running in the agent sandbox.

When ``REMI_API_URL`` is set, CLI commands use these helpers instead of
a local Container.  Only stdlib — no third-party dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def api_url() -> str | None:
    """Return the REMI API base URL if running in sandbox mode."""
    return os.environ.get("REMI_API_URL")


def is_sandbox() -> bool:
    """True when the CLI is running inside the agent sandbox."""
    return api_url() is not None


def get(path: str) -> Any:
    """GET /api/v1/{path} and return parsed JSON."""
    base = api_url()
    if not base:
        raise RuntimeError("REMI_API_URL not set")
    url = f"{base.rstrip('/')}/api/v1{path}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def post(path: str, body: dict[str, Any]) -> Any:
    """POST /api/v1/{path} with JSON body and return parsed JSON."""
    base = api_url()
    if not base:
        raise RuntimeError("REMI_API_URL not set")
    url = f"{base.rstrip('/')}/api/v1{path}"
    payload = json.dumps(body, default=str).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())
