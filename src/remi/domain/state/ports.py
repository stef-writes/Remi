"""State store port — the interface that persistence adapters implement."""

from __future__ import annotations

import abc

from remi.domain.state.models import ExecutionRecord, ModuleState, RunRecord
from remi.shared.ids import AppId, ModuleId, RunId


class StateStore(abc.ABC):
    """Port defining state persistence operations."""

    @abc.abstractmethod
    async def write_module_state(self, state: ModuleState) -> None: ...

    @abc.abstractmethod
    async def get_module_state(
        self, app_id: AppId, run_id: RunId, module_id: ModuleId
    ) -> ModuleState | None: ...

    @abc.abstractmethod
    async def get_upstream_outputs(
        self, app_id: AppId, run_id: RunId, module_ids: list[ModuleId]
    ) -> dict[ModuleId, ModuleState]: ...

    @abc.abstractmethod
    async def append_execution_record(self, record: ExecutionRecord) -> None: ...

    @abc.abstractmethod
    async def get_run_history(
        self, app_id: AppId, run_id: RunId
    ) -> list[ExecutionRecord]: ...

    @abc.abstractmethod
    async def write_run_record(self, record: RunRecord) -> None: ...

    @abc.abstractmethod
    async def get_run_record(self, app_id: AppId, run_id: RunId) -> RunRecord | None: ...

    @abc.abstractmethod
    async def get_all_module_states(
        self, app_id: AppId, run_id: RunId
    ) -> list[ModuleState]: ...
