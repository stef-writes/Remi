"""Domain models for execution state and history."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from remi.shared.enums import ModuleStatus, RunStatus

if TYPE_CHECKING:
    from datetime import datetime

    from remi.shared.ids import AppId, ModuleId, RunId


class ModuleState(BaseModel):
    """Current output of a module for a specific run."""

    app_id: AppId
    run_id: RunId
    module_id: ModuleId
    status: ModuleStatus
    output: Any | None = None
    contract: Any | None = None
    updated_at: datetime | None = None

    @property
    def contract_name(self) -> str | None:
        """Resolve the contract label regardless of stored type."""
        from remi.domain.modules.base import SemanticContract

        if self.contract is None:
            return None
        if isinstance(self.contract, SemanticContract):
            return self.contract.name
        if isinstance(self.contract, str):
            return self.contract
        if isinstance(self.contract, dict) and "name" in self.contract:
            return self.contract["name"]
        return str(self.contract)


class ExecutionRecord(BaseModel):
    """Detailed history entry for a single module execution attempt."""

    app_id: AppId
    run_id: RunId
    module_id: ModuleId
    attempt: int = 1
    status: ModuleStatus = ModuleStatus.PENDING
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    output_snapshot: Any | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    """Top-level record for an entire app run."""

    app_id: AppId
    run_id: RunId
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    module_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    tags: dict[str, str] = Field(default_factory=dict)
