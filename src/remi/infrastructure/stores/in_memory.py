"""In-memory state store — suitable for development, testing, and single-process use."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from remi.domain.state.ports import StateStore

if TYPE_CHECKING:
    from remi.domain.state.models import ExecutionRecord, ModuleState, RunRecord
    from remi.shared.ids import AppId, ModuleId, RunId


class InMemoryStateStore(StateStore):
    def __init__(self) -> None:
        self._module_states: dict[tuple[AppId, RunId, ModuleId], ModuleState] = {}
        self._execution_records: dict[tuple[AppId, RunId], list[ExecutionRecord]] = defaultdict(
            list
        )
        self._run_records: dict[tuple[AppId, RunId], RunRecord] = {}

    async def write_module_state(self, state: ModuleState) -> None:
        key = (state.app_id, state.run_id, state.module_id)
        self._module_states[key] = state

    async def get_module_state(
        self, app_id: AppId, run_id: RunId, module_id: ModuleId
    ) -> ModuleState | None:
        return self._module_states.get((app_id, run_id, module_id))

    async def get_upstream_outputs(
        self, app_id: AppId, run_id: RunId, module_ids: list[ModuleId]
    ) -> dict[ModuleId, ModuleState]:
        result: dict[ModuleId, ModuleState] = {}
        for mid in module_ids:
            state = self._module_states.get((app_id, run_id, mid))
            if state is not None:
                result[mid] = state
        return result

    async def append_execution_record(self, record: ExecutionRecord) -> None:
        key = (record.app_id, record.run_id)
        self._execution_records[key].append(record)

    async def get_run_history(
        self, app_id: AppId, run_id: RunId
    ) -> list[ExecutionRecord]:
        return list(self._execution_records.get((app_id, run_id), []))

    async def write_run_record(self, record: RunRecord) -> None:
        self._run_records[(record.app_id, record.run_id)] = record

    async def get_run_record(self, app_id: AppId, run_id: RunId) -> RunRecord | None:
        return self._run_records.get((app_id, run_id))

    async def get_all_module_states(
        self, app_id: AppId, run_id: RunId
    ) -> list[ModuleState]:
        return [
            state
            for (aid, rid, _), state in self._module_states.items()
            if aid == app_id and rid == run_id
        ]
