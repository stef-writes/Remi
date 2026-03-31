"""GraphRunner — the core execution engine that walks an app graph and runs modules."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

from remi.domain.graph.validation import topological_sort
from remi.domain.state.models import ExecutionRecord, ModuleState, RunRecord
from remi.runtime.context.runtime_context import RuntimeContext
from remi.runtime.events.lifecycle import (
    APP_OUTPUT_READY,
    MODULE_COMPLETED,
    MODULE_FAILED,
    MODULE_STARTED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    InterAppEvent,
    LifecycleEvent,
    ModuleEvent,
)
from remi.runtime.policies.retry import RetryPolicy
from remi.shared.clock import Clock, SystemClock
from remi.shared.enums import ModuleStatus, RunStatus
from remi.shared.errors import ExecutionError
from remi.shared.ids import AppId, ModuleId, RunId, new_run_id

if TYPE_CHECKING:
    from remi.domain.graph.definitions import AppDefinition
    from remi.domain.modules.ports import ModuleRegistry
    from remi.domain.state.ports import StateStore
    from remi.runtime.events.bus import EventBus

logger = structlog.get_logger(__name__)


class GraphRunner:
    """Orchestrates the execution of an app definition's module graph."""

    def __init__(
        self,
        module_registry: ModuleRegistry,
        state_store: StateStore,
        event_bus: EventBus,
        clock: Clock | None = None,
        retry_policy: RetryPolicy | None = None,
        context_extras: dict[str, Any] | None = None,
    ) -> None:
        self._modules = module_registry
        self._state = state_store
        self._events = event_bus
        self._clock = clock or SystemClock()
        self._retry = retry_policy or RetryPolicy(max_retries=1, delay_seconds=0)
        self._context_extras = context_extras or {}

    async def run(
        self,
        app: AppDefinition,
        *,
        run_id: RunId | None = None,
        start_from: ModuleId | None = None,
        tags: dict[str, str] | None = None,
        run_params: dict[str, Any] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> RunId:
        rid = run_id or new_run_id()
        extras: dict[str, Any] = {**self._context_extras}
        extras["graph_runner"] = self
        extras["state_store"] = self._state
        if run_params:
            extras["run_params"] = run_params
        if extra_context:
            extras.update(extra_context)
        ctx = RuntimeContext(
            app_id=app.app_id,
            run_id=rid,
            tags=tags or {},
            extras=extras,
        )

        is_agent_driven = app.settings.execution_mode == "agent_driven"

        if is_agent_driven:
            execution_order = await self._plan_agent_driven(app, ctx, run_params)
        else:
            execution_order = topological_sort(app)

        if start_from is not None:
            idx = execution_order.index(start_from) if start_from in execution_order else 0
            execution_order = execution_order[idx:]

        run_record = RunRecord(
            app_id=app.app_id,
            run_id=rid,
            status=RunStatus.RUNNING,
            started_at=self._clock.now(),
            module_count=len(execution_order),
        )
        await self._state.write_run_record(run_record)

        await self._events.publish(
            LifecycleEvent(
                event_type=RUN_STARTED,
                app_id=app.app_id,
                run_id=rid,
                timestamp=self._clock.now(),
            )
        )

        failed = False
        completed_count = 0
        failed_count = 0
        skipped: set[ModuleId] = set()

        for module_id in execution_order:
            module_def = app.get_module(module_id)
            if module_def is None:
                continue

            if module_id in skipped:
                continue

            if not await _edges_satisfied(app, module_id, self._state, app.app_id, rid):
                incoming = [e for e in app.edges if e.to_module == module_id]
                if any(e.condition for e in incoming):
                    skipped.add(module_id)
                    _propagate_skip(app, module_id, skipped)
                    logger.info("module_skipped_by_condition", module_id=module_id)
                    continue

            upstream_ids = app.get_upstream_ids(module_id)
            upstream_ids = [uid for uid in upstream_ids if uid not in skipped]
            upstream_states = await self._state.get_upstream_outputs(
                app.app_id, rid, upstream_ids
            )

            inputs = _assemble_inputs(upstream_states)

            module_instance = self._modules.build(module_def)

            validation_errors = module_instance.validate_inputs(inputs)
            if validation_errors:
                logger.warning(
                    "input_validation_failed",
                    module_id=module_id,
                    errors=validation_errors,
                )

            await self._events.publish(
                ModuleEvent(
                    event_type=MODULE_STARTED,
                    app_id=app.app_id,
                    run_id=rid,
                    module_id=module_id,
                    timestamp=self._clock.now(),
                )
            )

            started_at = self._clock.now()
            try:
                output = await self._retry.execute(module_instance.run, inputs, ctx)

                completed_at = self._clock.now()
                duration_ms = (completed_at - started_at).total_seconds() * 1000

                module_state = ModuleState(
                    app_id=app.app_id,
                    run_id=rid,
                    module_id=module_id,
                    status=ModuleStatus.COMPLETED,
                    output=output.value,
                    contract=output.contract_name,
                    updated_at=completed_at,
                )
                await self._state.write_module_state(module_state)

                record = ExecutionRecord(
                    app_id=app.app_id,
                    run_id=rid,
                    module_id=module_id,
                    status=ModuleStatus.COMPLETED,
                    input_snapshot=inputs,
                    output_snapshot=output.value,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    metadata=output.metadata,
                )
                await self._state.append_execution_record(record)

                await self._events.publish(
                    ModuleEvent(
                        event_type=MODULE_COMPLETED,
                        app_id=app.app_id,
                        run_id=rid,
                        module_id=module_id,
                        timestamp=completed_at,
                        metadata={"contract": output.contract_name, "output": output.value},
                    )
                )

                completed_count += 1

                logger.info(
                    "module_completed",
                    module_id=module_id,
                    kind=module_def.kind,
                    duration_ms=round(duration_ms, 2),
                )

            except Exception as exc:
                completed_at = self._clock.now()
                duration_ms = (completed_at - started_at).total_seconds() * 1000

                module_state = ModuleState(
                    app_id=app.app_id,
                    run_id=rid,
                    module_id=module_id,
                    status=ModuleStatus.FAILED,
                    updated_at=completed_at,
                )
                await self._state.write_module_state(module_state)

                record = ExecutionRecord(
                    app_id=app.app_id,
                    run_id=rid,
                    module_id=module_id,
                    status=ModuleStatus.FAILED,
                    input_snapshot=inputs,
                    error=str(exc),
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                )
                await self._state.append_execution_record(record)

                await self._events.publish(
                    ModuleEvent(
                        event_type=MODULE_FAILED,
                        app_id=app.app_id,
                        run_id=rid,
                        module_id=module_id,
                        timestamp=completed_at,
                        error=str(exc),
                    )
                )

                failed = True
                failed_count += 1
                logger.error(
                    "module_failed",
                    module_id=module_id,
                    kind=module_def.kind,
                    error=str(exc),
                )
                raise ExecutionError(str(exc), module_id=module_id) from exc

        final_status = RunStatus.FAILED if failed else RunStatus.COMPLETED
        run_record = RunRecord(
            app_id=app.app_id,
            run_id=rid,
            status=final_status,
            started_at=run_record.started_at,
            completed_at=self._clock.now(),
            module_count=len(execution_order),
            completed_count=completed_count,
            failed_count=failed_count,
            tags=tags or {},
        )
        await self._state.write_run_record(run_record)

        event_type = RUN_COMPLETED if not failed else RUN_FAILED
        await self._events.publish(
            LifecycleEvent(
                event_type=event_type,
                app_id=app.app_id,
                run_id=rid,
                timestamp=self._clock.now(),
            )
        )

        if not failed:
            await self._events.publish_inter_app(
                InterAppEvent(
                    event_type=APP_OUTPUT_READY,
                    app_id=app.app_id,
                    run_id=rid,
                    timestamp=self._clock.now(),
                    source_app_id=app.app_id,
                    payload={"run_id": rid, "status": "completed"},
                )
            )

        return rid


    async def _plan_agent_driven(
        self,
        app: AppDefinition,
        ctx: RuntimeContext,
        run_params: dict[str, Any] | None,
    ) -> list[ModuleId]:
        """Use the designated planner module to decide execution order.

        The planner agent receives a description of all available modules and
        must return a JSON list of module IDs to execute in order.  Falls back
        to topological sort if the planner is missing or fails.
        """
        planner_id = app.settings.planner_module
        if not planner_id:
            logger.warning("agent_driven_mode_no_planner", app_id=app.app_id)
            return topological_sort(app)

        planner_def = app.get_module(planner_id)
        if planner_def is None:
            logger.warning("planner_module_not_found", planner_id=planner_id)
            return topological_sort(app)

        available_modules = [
            m.to_llm_description()
            for m in app.modules
            if m.id != planner_id
        ]
        planner_input = {
            "available_modules": "\n\n".join(available_modules),
            "goal": (run_params or {}).get("goal", "Execute the app graph"),
            "app_description": app.metadata.to_llm_description(),
        }

        try:
            planner_instance = self._modules.build(planner_def)
            output = await planner_instance.run(planner_input, ctx)

            plan = output.value
            if isinstance(plan, list):
                ordered = [ModuleId(mid) for mid in plan if app.get_module(ModuleId(mid))]
                if ordered:
                    logger.info("agent_driven_plan", plan=ordered)
                    return ordered
            if isinstance(plan, dict) and "modules" in plan:
                ordered = [ModuleId(mid) for mid in plan["modules"] if app.get_module(ModuleId(mid))]
                if ordered:
                    logger.info("agent_driven_plan", plan=ordered)
                    return ordered

            logger.warning("planner_returned_invalid_plan", output=plan)
        except Exception as exc:
            logger.error("planner_failed", error=str(exc))

        return topological_sort(app)


async def _edges_satisfied(
    app: AppDefinition,
    module_id: ModuleId,
    state_store: StateStore,
    app_id: AppId,
    run_id: RunId,
) -> bool:
    """Check if all incoming edges with conditions are satisfied.

    Condition syntax: ``contract:<label>`` — the upstream module's output
    contract must match the label.
    """
    incoming = [e for e in app.edges if e.to_module == module_id]
    for edge in incoming:
        if not edge.condition:
            continue
        match = re.match(r"^contract:(.+)$", edge.condition)
        if not match:
            continue
        expected_label = match.group(1)
        upstream_state = await state_store.get_module_state(app_id, run_id, edge.from_module)
        if upstream_state is None:
            return False
        if upstream_state.contract_name != f"route:{expected_label}":
            return False
    return True


def _propagate_skip(
    app: AppDefinition, module_id: ModuleId, skipped: set[ModuleId]
) -> None:
    """Recursively skip all downstream modules of a skipped node."""
    for downstream_id in app.get_downstream_ids(module_id):
        if downstream_id not in skipped:
            skipped.add(downstream_id)
            _propagate_skip(app, downstream_id, skipped)


def _assemble_inputs(
    upstream_states: dict[ModuleId, ModuleState],
) -> dict[str, Any]:
    """Build the inputs dict for a module.

    If all upstream outputs are conversation threads, merge them into a
    single ``thread`` key so agent nodes see one unified conversation.
    Otherwise, pass each upstream output keyed by module_id.
    """
    active = {
        mid: state for mid, state in upstream_states.items() if state.output is not None
    }

    if not active:
        return {}

    all_conversations = all(
        state.contract_name == "conversation" for state in active.values()
    )

    if all_conversations:
        merged = _merge_threads(active)
        return {"thread": merged}

    return {mid: state.output for mid, state in active.items()}


def _merge_threads(
    states: dict[ModuleId, ModuleState],
) -> list[dict[str, Any]]:
    """Merge multiple conversation threads into one, deduplicating messages."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    for _mid, state in states.items():
        thread = state.output
        if not isinstance(thread, list):
            continue
        for msg in thread:
            if not isinstance(msg, dict):
                continue
            fingerprint = f"{msg.get('role')}:{msg.get('name')}:{str(msg.get('content'))[:200]}"
            if fingerprint not in seen:
                seen.add(fingerprint)
                merged.append(msg)

    return merged
