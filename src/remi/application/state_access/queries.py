"""Query service for reading execution state and history."""

from __future__ import annotations

from remi.domain.state.models import ExecutionRecord, ModuleState, RunRecord
from remi.domain.state.ports import StateStore
from remi.shared.ids import AppId, ModuleId, RunId


class StateQueryService:
    def __init__(self, state_store: StateStore) -> None:
        self._store = state_store

    async def get_module_state(
        self, app_id: AppId, run_id: RunId, module_id: ModuleId
    ) -> ModuleState | None:
        return await self._store.get_module_state(app_id, run_id, module_id)

    async def get_run_history(self, app_id: AppId, run_id: RunId) -> list[ExecutionRecord]:
        return await self._store.get_run_history(app_id, run_id)

    async def get_run_record(self, app_id: AppId, run_id: RunId) -> RunRecord | None:
        return await self._store.get_run_record(app_id, run_id)

    async def get_all_module_states(
        self, app_id: AppId, run_id: RunId
    ) -> list[ModuleState]:
        return await self._store.get_all_module_states(app_id, run_id)
