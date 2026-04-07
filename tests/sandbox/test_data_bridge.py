"""Tests for the remi SDK (application/sdk.py).

The SDK is a real .py file that gets copied into each sandbox session.
These tests verify its functions hit the right endpoints, query strings
are built correctly, and errors are handled cleanly.
"""

from __future__ import annotations

import importlib
import json
import os
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

import pytest


def _load_sdk(api_url: str) -> types.ModuleType:
    """Load the SDK in an isolated module namespace pointing at *api_url*."""
    import remi.application.sdk as sdk_module

    source_path = sdk_module.__file__
    assert source_path is not None

    mod = types.ModuleType("remi")
    mod.__dict__["__builtins__"] = __builtins__
    old_env = os.environ.get("REMI_API_URL")
    os.environ["REMI_API_URL"] = api_url
    try:
        with open(source_path) as f:
            exec(compile(f.read(), "remi.py", "exec"), mod.__dict__)
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

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _MockHandler.requests.append(f"POST {self.path} {body.decode()}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def mock_api():
    _MockHandler.requests = []
    _MockHandler.response_data = {}

    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}", _MockHandler

    server.shutdown()


def test_sdk_is_valid_python() -> None:
    """SDK module compiles and imports without errors."""
    mod = importlib.import_module("remi.application.sdk")
    assert hasattr(mod, "managers")
    assert hasattr(mod, "properties")
    assert hasattr(mod, "search")


def test_sdk_managers(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {"managers": [{"id": "m1", "name": "Jake"}]}

    sdk = _load_sdk(url)
    result = sdk.managers()

    assert len(result) == 1
    assert result[0]["name"] == "Jake"
    assert any("/api/v1/managers" in r for r in handler.requests)


def test_sdk_properties_with_name_resolution(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {
        "managers": [{"id": "m1", "name": "Jake Kraus"}],
        "properties": [{"id": "p1", "name": "Elm St"}],
    }

    sdk = _load_sdk(url)
    result = sdk.properties(manager="Jake Kraus")

    assert any("/api/v1/properties" in r for r in handler.requests)


def test_sdk_rent_roll(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {
        "properties": [{"id": "p1", "name": "Elm St"}],
        "property_id": "p1",
        "rows": [{"unit_id": "u1", "market_rent": 1500}],
    }

    sdk = _load_sdk(url)
    result = sdk.rent_roll("Elm St")

    assert "rows" in result
    assert any("rent-roll" in r for r in handler.requests)


def test_sdk_handles_connection_error() -> None:
    sdk = _load_sdk("http://127.0.0.1:1")
    with pytest.raises(ConnectionError, match="Cannot reach REMI API"):
        sdk.managers()


def test_sdk_search(mock_api: tuple) -> None:
    url, handler = mock_api
    handler.response_data = {"results": [{"entity_id": "t1", "label": "Smith"}]}

    sdk = _load_sdk(url)
    result = sdk.search("Smith")

    assert len(result) == 1
    matched = [r for r in handler.requests if "/api/v1/search" in r]
    assert matched
    assert "q=Smith" in matched[0]
