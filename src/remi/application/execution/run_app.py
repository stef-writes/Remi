"""Use case: orchestrate a full or partial app run."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from remi.application.app_management.ports import AppRegistry
from remi.shared.enums import RunStatus
from remi.shared.errors import AppNotFoundError
from remi.shared.ids import AppId, ModuleId, RunId, new_run_id

if TYPE_CHECKING:
    from remi.runtime.engine.graph_runner import GraphRunner


class RunAppResult:
    def __init__(self, run_id: RunId, status: RunStatus, errors: list[str] | None = None) -> None:
        self.run_id = run_id
        self.status = status
        self.errors = errors or []


class RunAppUseCase:
    def __init__(self, app_registry: AppRegistry, graph_runner: GraphRunner) -> None:
        self._app_registry = app_registry
        self._graph_runner = graph_runner

    async def execute(
        self,
        app_id: AppId,
        *,
        run_id: RunId | None = None,
        start_from: ModuleId | None = None,
        tags: dict[str, str] | None = None,
        run_params: dict[str, Any] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> RunAppResult:
        app = self._app_registry.get(app_id)
        if app is None:
            raise AppNotFoundError(app_id)

        rid = run_id or new_run_id()

        try:
            await self._graph_runner.run(
                app,
                run_id=rid,
                start_from=start_from,
                tags=tags,
                run_params=run_params,
                extra_context=extra_context,
            )
            return RunAppResult(run_id=rid, status=RunStatus.COMPLETED)
        except Exception as exc:
            return RunAppResult(
                run_id=rid, status=RunStatus.FAILED, errors=[str(exc)]
            )
