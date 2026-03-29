"""Request/response schemas for platform endpoints (apps, runs, health)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RegisterAppRequest(BaseModel):
    definition: dict[str, Any] | None = None
    yaml_path: str | None = None


class RegisterAppResponse(BaseModel):
    app_id: str
    name: str
    version: str
    module_count: int


class RunAppRequest(BaseModel):
    start_from: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)


class RunAppResponse(BaseModel):
    run_id: str
    status: str
    errors: list[str] = Field(default_factory=list)


class AppSummary(BaseModel):
    app_id: str
    name: str
    version: str
    module_count: int
    edge_count: int


class ModuleStateResponse(BaseModel):
    app_id: str
    run_id: str
    module_id: str
    status: str
    output: Any | None = None
    contract: str | None = None


class ExecutionRecordResponse(BaseModel):
    module_id: str
    attempt: int
    status: str
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None


class RunHistoryResponse(BaseModel):
    app_id: str
    run_id: str
    records: list[ExecutionRecordResponse]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class ErrorResponse(BaseModel):
    error: str
    code: str | None = None
    details: list[str] = Field(default_factory=list)
