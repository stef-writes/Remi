"""ChatAgentService — run agents in single-shot or multi-turn chat mode.

Both ``ask`` (single-shot) and ``run_chat_agent`` (multi-turn) go through
the full ``GraphRunner`` path — same context, same lifecycle events, same
retry policy. Per-request extras like ``on_event`` and ``sandbox_session_id``
are passed via ``extra_context`` so the agent node receives them alongside
the container-level extras.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol

from remi.infrastructure.loaders.yaml_loader import YamlAppLoader
from remi.shared.ids import AppId, ModuleId
from remi.shared.paths import WORKFLOWS_DIR

if TYPE_CHECKING:
    from remi.application.app_management.register_app import RegisterAppUseCase
    from remi.application.execution.run_app import RunAppUseCase
    from remi.application.state_access.queries import StateQueryService
    from remi.domain.chat.ports import ChatSessionStore
    from remi.domain.graph.definitions import AppDefinition


class EventCallback(Protocol):
    async def __call__(self, event_type: str, data: dict[str, Any]) -> None: ...


class ChatAgentService:
    """Runs agents for single-shot /ask and multi-turn chat.

    Both methods load the app YAML, register it, and execute through
    ``RunAppUseCase`` → ``GraphRunner``. The graph runner provides
    the full ``RuntimeContext`` (all container extras), lifecycle events,
    state persistence, and retry — no parallel code path.
    """

    def __init__(
        self,
        register_app_uc: RegisterAppUseCase,
        run_app_uc: RunAppUseCase,
        state_query: StateQueryService,
        chat_session_store: ChatSessionStore,
    ) -> None:
        self._register_app_uc = register_app_uc
        self._run_app_uc = run_app_uc
        self._state_query = state_query
        self._chat_session_store = chat_session_store

    def _load_and_register(self, agent_name: str) -> Any:
        """Load app YAML and register it. Returns the AppDefinition."""

        app_path = WORKFLOWS_DIR / agent_name / "app.yaml"
        if not app_path.exists():
            raise ValueError(f"Unknown agent: {agent_name}")

        loader = YamlAppLoader()
        app_def: AppDefinition = loader.load(str(app_path))

        reg_result = self._register_app_uc.execute(app_def)
        if reg_result.is_err:
            raise RuntimeError(f"Registration failed: {reg_result.unwrap_err()}")

        return app_def

    async def ask(self, agent_name: str, question: str) -> tuple[str | None, str]:
        """Single-shot agent invocation. Returns (answer, run_id)."""
        app_def = self._load_and_register(agent_name)

        result = await self._run_app_uc.execute(
            AppId(app_def.app_id),
            run_params={"input": question},
        )

        agent_modules = [m.id for m in app_def.modules if m.kind == "agent"]
        output_mid = agent_modules[-1] if agent_modules else app_def.modules[-1].id

        state = await self._state_query.get_module_state(
            AppId(app_def.app_id), result.run_id, ModuleId(output_mid)
        )

        return (state.output if state else None, result.run_id)

    async def run_chat_agent(
        self,
        agent_name: str,
        thread: list[Any],
        on_event: EventCallback | None = None,
        *,
        sandbox_session_id: str | None = None,
    ) -> str:
        """Multi-turn agent execution over a message thread.

        Goes through the full GraphRunner path. Per-request extras
        (on_event, sandbox_session_id) are injected via extra_context.
        """
        from remi.domain.modules.base import Message

        app_def = self._load_and_register(agent_name)

        thread_msgs: list[dict[str, Any]] = []
        for msg in thread:
            if isinstance(msg, Message):
                thread_msgs.append(msg.model_dump())
            elif isinstance(msg, dict):
                thread_msgs.append(msg)
            else:
                thread_msgs.append({"role": "user", "content": str(msg)})

        per_request_extras: dict[str, Any] = {}
        if on_event is not None:
            per_request_extras["on_event"] = on_event
        if sandbox_session_id is not None:
            per_request_extras["sandbox_session_id"] = sandbox_session_id

        result = await self._run_app_uc.execute(
            AppId(app_def.app_id),
            run_params={"thread": thread_msgs},
            extra_context=per_request_extras,
        )

        agent_modules = [m.id for m in app_def.modules if m.kind == "agent"]
        output_mid = agent_modules[-1] if agent_modules else app_def.modules[-1].id

        state = await self._state_query.get_module_state(
            AppId(app_def.app_id), result.run_id, ModuleId(output_mid)
        )

        if state is None or state.output is None:
            return ""

        output = state.output
        if isinstance(output, str):
            return output
        if isinstance(output, list):
            for msg in reversed(output):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "")
            return json.dumps(output, default=str)
        return json.dumps(output, default=str)
