"""Tests for the auto-generated data bridge (remi_data.py).

The bridge source is a Python string that gets written into each sandbox
session. These tests verify it compiles, its HTTP calls target the right
endpoints, query strings are built correctly, and errors are handled cleanly.
"""

from __future__ import annotations

import json
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

import pytest

from remi.sandbox.data_bridge import DATA_BRIDGE_SOURCE

# -- US-4 prerequisite: bridge is valid Python --------------------------------

def test_bridge_source_is_valid_python() -> None:
    """DATA_BRIDGE_SOURCE must compile without syntax errors."""
    code = compile(DATA_BRIDGE_SOURCE, "remi_data.py", "exec")
    assert code is not None


def _load_bridge(api_url: str) -> types.ModuleType:
    """Execute the bridge source in an isolated module namespace."""
    import os

    mod = types.ModuleType("remi_data")
    mod.__dict__["__builtins__"] = __builtins__
    old_env = os.environ.get("REMI_API_URL")
    os.environ["REMI_API_URL"] = api_url
    try:
        exec(compile(DATA_BRIDGE_SOURCE, "remi_data.py", "exec"), mod.__dict__)
    finally:
        if old_env is None:
            os.environ.pop("REMI_API_URL", None)
        else:
            os.environ["REMI_API_URL"] = old_env
    return mod


class _MockHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that records requests and returns canned JSON."""

    requests: list[str] = []
    response_data: dict[str, Any] = {}

    def do_GET(self) -> None:
        _MockHandler.requests.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(_MockHandler.response_data).encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def mock_api():
    """Start a local HTTP server that records requests."""
    _MockHandler.requests = []
    _MockHandler.response_data = {}

    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}", _MockHandler

    server.shutdown()


# -- US-4: bridge functions hit correct endpoints -----------------------------

def test_bridge_properties_function(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {"properties": [{"id": "p1", "name": "Elm St"}]}

    bridge = _load_bridge(url)
    result = bridge.properties()

    assert len(result) == 1
    assert result[0]["id"] == "p1"
    assert any("/api/v1/properties" in r for r in handler.requests)


def test_bridge_units_with_filters(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {"units": [{"id": "u1", "status": "vacant"}]}

    bridge = _load_bridge(url)
    result = bridge.units(property_id="p1", status="vacant")

    assert len(result) == 1
    matched = [r for r in handler.requests if "/api/v1/units" in r]
    assert matched, "Should have hit /units endpoint"
    assert "property_id=p1" in matched[0]
    assert "status=vacant" in matched[0]


def test_bridge_rent_roll(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {
        "property_id": "p1",
        "rows": [{"unit_id": "u1", "market_rent": 1500}],
    }

    bridge = _load_bridge(url)
    result = bridge.rent_roll("p1")

    assert "rows" in result
    assert result["rows"][0]["market_rent"] == 1500
    assert any("/api/v1/properties/p1/rent-roll" in r for r in handler.requests)


# -- Error handling -----------------------------------------------------------

def test_bridge_handles_connection_error() -> None:
    bridge = _load_bridge("http://127.0.0.1:1")
    with pytest.raises(ConnectionError, match="Cannot reach REMI API"):
        bridge.properties()


# -- Query string construction ------------------------------------------------

def test_bridge_query_string_skips_none(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {"signals": []}

    bridge = _load_bridge(url)
    bridge.signals(severity="high")

    matched = [r for r in handler.requests if "/api/v1/signals" in r]
    assert matched
    assert "severity=high" in matched[0]
    assert "manager_id" not in matched[0]
    assert "property_id" not in matched[0]


def test_bridge_managers_endpoint(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {"managers": [{"id": "m1", "name": "Jake"}]}

    bridge = _load_bridge(url)
    result = bridge.managers()

    assert len(result) == 1
    assert result[0]["name"] == "Jake"
    assert any("/api/v1/managers" in r for r in handler.requests)
