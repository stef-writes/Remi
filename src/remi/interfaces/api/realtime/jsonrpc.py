"""JSON-RPC 2.0 protocol primitives for WebSocket communication.

Implements the JSON-RPC 2.0 spec (https://www.jsonrpc.org/specification)
with message types, error codes, and a lightweight method dispatcher.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel, Field

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
AGENT_ERROR = -32001


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: str | int | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Any = None
    id: str | int | None = None

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=False)


class JsonRpcError(BaseModel):
    jsonrpc: str = "2.0"
    error: dict[str, Any]
    id: str | int | None = None

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=False)

    @classmethod
    def from_code(
        cls,
        code: int,
        message: str,
        data: Any = None,
        request_id: str | int | None = None,
    ) -> JsonRpcError:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return cls(error=err, id=request_id)


class JsonRpcNotification(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json()


MethodHandler = Callable[..., Coroutine[Any, Any, Any]]


class Dispatcher:
    """Route JSON-RPC method names to async handler functions."""

    def __init__(self) -> None:
        self._methods: dict[str, MethodHandler] = {}

    def register(self, method: str, handler: MethodHandler) -> None:
        self._methods[method] = handler

    def method(self, name: str) -> Callable[[MethodHandler], MethodHandler]:
        def decorator(fn: MethodHandler) -> MethodHandler:
            self._methods[name] = fn
            return fn
        return decorator

    async def dispatch(self, raw: str) -> JsonRpcResponse | JsonRpcError:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return JsonRpcError.from_code(PARSE_ERROR, "Parse error")

        try:
            request = JsonRpcRequest.model_validate(data)
        except Exception:
            return JsonRpcError.from_code(
                INVALID_REQUEST, "Invalid request", request_id=data.get("id")
            )

        handler = self._methods.get(request.method)
        if handler is None:
            return JsonRpcError.from_code(
                METHOD_NOT_FOUND,
                f"Method not found: {request.method}",
                request_id=request.id,
            )

        try:
            result = await handler(request)
            return JsonRpcResponse(result=result, id=request.id)
        except Exception as exc:
            return JsonRpcError.from_code(
                AGENT_ERROR,
                str(exc),
                request_id=request.id,
            )
