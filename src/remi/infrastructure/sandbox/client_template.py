"""Sandbox-side REMI client — seeded into sandbox sessions at startup.

This module is written into the sandbox working directory as ``remi_client.py``.
It has ZERO dependencies on the remi package — only stdlib. Sandbox scripts
import it to query the live ontology API instead of reading stale CSV snapshots.

Usage in sandbox scripts::

    from remi_client import remi

    # Synchronous (simple scripts)
    managers = remi.search("PropertyManager")
    unit = remi.get("Unit", "unit-42")
    count = remi.aggregate("Lease", "count")
    signals = remi.signals()

    # Async (when running in an async context)
    managers = await remi.async_search("PropertyManager")
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

_BASE_URL = os.environ.get("REMI_API_URL", "http://127.0.0.1:8000")
_PREFIX = f"{_BASE_URL}/api/v1"


class _RemiClient:
    """Lightweight synchronous client for the REMI API.

    Uses only stdlib urllib — no external dependencies required.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or _BASE_URL).rstrip("/")
        self._prefix = f"{self._base}/api/v1"

    # -- Ontology queries -----------------------------------------------------

    def search(
        self,
        type_name: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search objects of any type with optional filters."""
        if filters:
            data = self._post(f"/ontology/search/{type_name}", {
                "filters": filters, "order_by": order_by, "limit": limit,
            })
        else:
            params = f"?limit={limit}"
            if order_by:
                params += f"&order_by={urllib.request.quote(order_by)}"
            data = self._get(f"/ontology/search/{type_name}{params}")
        return data["objects"]

    def get(self, type_name: str, object_id: str) -> dict[str, Any] | None:
        """Get a single object by type and ID."""
        try:
            data = self._get(f"/ontology/objects/{type_name}/{object_id}")
            return data.get("object")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def related(
        self,
        object_id: str,
        *,
        link_type: str | None = None,
        direction: str = "both",
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Find related objects via link traversal."""
        params = f"?direction={direction}&max_depth={max_depth}"
        if link_type:
            params += f"&link_type={urllib.request.quote(link_type)}"
        data = self._get(f"/ontology/related/{object_id}{params}")
        return data.get("nodes") or data.get("links") or []

    def aggregate(
        self,
        type_name: str,
        metric: str = "count",
        field: str | None = None,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> Any:
        """Compute aggregate metrics across objects."""
        data = self._post(f"/ontology/aggregate/{type_name}", {
            "metric": metric, "field": field,
            "filters": filters, "group_by": group_by,
        })
        return data["result"]

    def timeline(
        self,
        type_name: str,
        object_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get event history for an object."""
        data = self._get(f"/ontology/timeline/{type_name}/{object_id}?limit={limit}")
        return data["events"]

    def schema(self, type_name: str | None = None) -> dict[str, Any]:
        """Describe object types. Pass type_name for a single type, or None for all."""
        if type_name:
            return self._get(f"/ontology/schema/{type_name}")
        return self._get("/ontology/schema")

    def codify(
        self,
        knowledge_type: str,
        data: dict[str, Any],
        *,
        provenance: str = "inferred",
    ) -> str:
        """Codify operational knowledge. Returns the entity ID."""
        resp = self._post("/ontology/codify", {
            "knowledge_type": knowledge_type,
            "data": data,
            "provenance": provenance,
        })
        return resp["entity_id"]

    # -- Signals (convenience — hits the signals router, not ontology) --------

    def signals(
        self,
        *,
        manager_id: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        """List active entailed signals."""
        params_parts: list[str] = []
        if manager_id:
            params_parts.append(f"manager_id={urllib.request.quote(manager_id)}")
        if severity:
            params_parts.append(f"severity={urllib.request.quote(severity)}")
        qs = f"?{'&'.join(params_parts)}" if params_parts else ""
        data = self._get(f"/signals{qs}")
        return data["signals"]

    # -- HTTP helpers ---------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._prefix}{path}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())  # type: ignore[no-any-return]

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._prefix}{path}"
        payload = json.dumps(body, default=str).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())  # type: ignore[no-any-return]


# Module-level singleton — sandbox scripts do ``from remi_client import remi``
remi = _RemiClient()
