"""Platform endpoints — apps, runs, health."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from remi.interfaces.api.dependencies import get_container
from remi.interfaces.api.platform.schemas import (
    AppSummary,
    ErrorResponse,
    ExecutionRecordResponse,
    HealthResponse,
    ModuleStateResponse,
    RegisterAppRequest,
    RegisterAppResponse,
    RunAppRequest,
    RunAppResponse,
    RunHistoryResponse,
)
from remi.shared.errors import AppNotFoundError
from remi.shared.ids import AppId, ModuleId, RunId

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(tags=["platform"])


# -- Health --

@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse()


# -- Apps --

@router.post(
    "/apps",
    response_model=RegisterAppResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}},
)
def register_app(
    body: RegisterAppRequest,
    container: Container = Depends(get_container),
) -> RegisterAppResponse:
    from remi.infrastructure.loaders.yaml_loader import YamlAppLoader

    loader = YamlAppLoader()
    try:
        if body.yaml_path:
            app_def = loader.load(body.yaml_path)
        elif body.definition:
            app_def = loader.parse(body.definition)
        else:
            raise HTTPException(status_code=400, detail="Provide either 'definition' (dict) or 'yaml_path' (string).")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = container.register_app_uc.execute(app_def)
    if result.is_err:
        raise HTTPException(status_code=400, detail=result.unwrap_err())

    app = result.unwrap()
    return RegisterAppResponse(
        app_id=app.app_id,
        name=app.metadata.name,
        version=app.metadata.version,
        module_count=len(app.modules),
    )


@router.get("/apps", response_model=list[AppSummary])
def list_apps(container: Container = Depends(get_container)) -> list[AppSummary]:
    apps = container.app_registry.list_apps()
    return [
        AppSummary(
            app_id=a.app_id,
            name=a.metadata.name,
            version=a.metadata.version,
            module_count=len(a.modules),
            edge_count=len(a.edges),
        )
        for a in apps
    ]


@router.get(
    "/apps/{app_id}",
    response_model=AppSummary,
    responses={404: {"model": ErrorResponse}},
)
def get_app(
    app_id: str,
    container: Container = Depends(get_container),
) -> AppSummary:
    app = container.app_registry.get(AppId(app_id))
    if app is None:
        raise HTTPException(status_code=404, detail=f"App not found: {app_id}")
    return AppSummary(
        app_id=app.app_id,
        name=app.metadata.name,
        version=app.metadata.version,
        module_count=len(app.modules),
        edge_count=len(app.edges),
    )


# -- Runs --

@router.post(
    "/runs/{app_id}",
    response_model=RunAppResponse,
    status_code=202,
    responses={404: {"model": ErrorResponse}},
)
async def run_app(
    app_id: str,
    body: RunAppRequest | None = None,
    container: Container = Depends(get_container),
) -> RunAppResponse:
    req = body or RunAppRequest()
    start_from = ModuleId(req.start_from) if req.start_from else None

    try:
        result = await container.run_app_uc.execute(
            AppId(app_id),
            start_from=start_from,
            tags=req.tags,
            run_params=req.params or None,
        )
    except AppNotFoundError:
        raise HTTPException(status_code=404, detail=f"App not found: {app_id}")

    return RunAppResponse(
        run_id=result.run_id,
        status=result.status.value,
        errors=result.errors,
    )


@router.get(
    "/runs/{app_id}/{run_id}/modules/{module_id}",
    response_model=ModuleStateResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_module_state(
    app_id: str,
    run_id: str,
    module_id: str,
    container: Container = Depends(get_container),
) -> ModuleStateResponse:
    state = await container.state_query.get_module_state(
        AppId(app_id), RunId(run_id), ModuleId(module_id)
    )
    if state is None:
        raise HTTPException(status_code=404, detail="Module state not found")

    return ModuleStateResponse(
        app_id=state.app_id,
        run_id=state.run_id,
        module_id=state.module_id,
        status=state.status.value,
        output=state.output,
        contract=state.contract,
    )


@router.get(
    "/runs/{app_id}/{run_id}/outputs",
    response_model=list[ModuleStateResponse],
)
async def get_run_outputs(
    app_id: str,
    run_id: str,
    container: Container = Depends(get_container),
) -> list[ModuleStateResponse]:
    states = await container.state_query.get_all_module_states(
        AppId(app_id), RunId(run_id)
    )
    return [
        ModuleStateResponse(
            app_id=s.app_id,
            run_id=s.run_id,
            module_id=s.module_id,
            status=s.status.value,
            output=s.output,
            contract=s.contract,
        )
        for s in states
    ]


@router.get(
    "/runs/{app_id}/{run_id}/history",
    response_model=RunHistoryResponse,
)
async def get_run_history(
    app_id: str,
    run_id: str,
    container: Container = Depends(get_container),
) -> RunHistoryResponse:
    records = await container.state_query.get_run_history(AppId(app_id), RunId(run_id))
    return RunHistoryResponse(
        app_id=app_id,
        run_id=run_id,
        records=[
            ExecutionRecordResponse(
                module_id=r.module_id,
                attempt=r.attempt,
                status=r.status.value,
                error=r.error,
                started_at=r.started_at.isoformat() if r.started_at else None,
                completed_at=r.completed_at.isoformat() if r.completed_at else None,
                duration_ms=r.duration_ms,
            )
            for r in records
        ],
    )
