"""AgentRuntime — run named agents in single-shot or multi-turn chat.

Lean invocation facade. Loads agent configs from YAML manifests, builds
runtime contexts, and delegates execution to ``AgentNode``. Session
state management lives in ``AgentSessions`` — this module only invokes.

Every request goes through the agent loop. The LLM decides how to
handle the question — fast tool calls for simple lookups, delegation
for deep analysis. No pre-LLM routing.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Protocol

import structlog
import yaml

from remi.agent.context.builder import ContextBuilder
from remi.agent.isolation import WorkspaceContext
from remi.agent.llm.types import ProviderFactory
from remi.agent.memory.store import MemoryStore
from remi.agent.memory.types import RecallService
from remi.agent.observe.types import Tracer
from remi.agent.observe.usage import LLMUsageLedger
from remi.agent.runtime.base import ModuleOutput
from remi.agent.runtime.config import RuntimeConfig
from remi.agent.runtime.deps import RunDeps, RunParams, RuntimeContext, ScopeContext
from remi.agent.runtime.node import AgentNode
from remi.agent.runtime.retry import RetryPolicy
from remi.agent.runtime.sessions import AgentSessions
from remi.agent.sandbox.types import Sandbox
from remi.agent.signals import DomainSchema, DomainTBox
from remi.agent.types import ChatSessionStore, ToolRegistry
from remi.agent.types import Message as ChatMessage
from remi.agent.workflow.loader import load_manifest_runtime
from remi.agent.workflow.registry import get_manifest_path
from remi.types.errors import SessionNotFoundError
from remi.types.ids import new_run_id

logger = structlog.get_logger("remi.runner")


class EventCallback(Protocol):
    async def __call__(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None: ...


class AgentRuntime:
    """Runs any named agent — stateless or session-aware.

    ``ask()`` is the single entry point. Every request goes through
    the agent loop — the LLM decides how to handle the question using
    its tool surface (query, search, documents, delegation, etc.).
    """

    def __init__(
        self,
        provider_factory: ProviderFactory,
        tool_registry: ToolRegistry,
        sandbox: Sandbox,
        memory_store: MemoryStore,
        tracer: Tracer,
        chat_session_store: ChatSessionStore,
        retry_policy: RetryPolicy,
        default_provider: str,
        default_model: str,
        domain_tbox: DomainTBox | None = None,
        context_builder: ContextBuilder | None = None,
        usage_ledger: LLMUsageLedger | None = None,
        recall_service: RecallService | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._tool_registry = tool_registry
        self._sandbox = sandbox
        self._domain_tbox = domain_tbox or DomainSchema()
        self._memory_store = memory_store
        self._tracer = tracer
        self._retry = retry_policy
        self._default_provider = default_provider
        self._default_model = default_model
        self._context_builder = context_builder
        self._usage_ledger = usage_ledger
        self._recall_service = recall_service
        self._result_schema_fn: Any = None

        self.sessions = AgentSessions(chat_session_store)

    def set_context_builder(self, builder: ContextBuilder) -> None:
        """Replace the context builder after construction.

        Products call this to inject a richer context builder that
        includes a domain-specific world model, profile fields, etc.
        """
        self._context_builder = builder

    def set_result_schema_fn(self, fn: Any) -> None:
        """Inject a domain-specific result-schema inference function.

        The callable receives ``(tool_name, arguments)`` and returns a
        schema label string or ``None``. It is forwarded to the agent loop
        so tool results can be tagged with the right frontend card schema
        without embedding domain knowledge in the kernel.

        Products (e.g. the REMI container) call this after construction to
        wire in their application-layer implementation.
        """
        self._result_schema_fn = fn

    def get_runtime_config(self, agent_name: str) -> RuntimeConfig:
        """Return the ``RuntimeConfig`` for a registered agent manifest."""
        return load_manifest_runtime(agent_name)

    # -- Public API --------------------------------------------------------

    async def ask(
        self,
        agent_name: str,
        question: str,
        *,
        session_id: str | None = None,
        on_event: EventCallback | None = None,
        scope: ScopeContext | None = None,
        mode: str = "agent",
        task_id: str | None = None,
    ) -> tuple[str | None, str]:
        """Run an agent. Returns ``(answer, run_id)``.

        Session-aware calls go through the multi-turn chat path.
        Everything else goes through the single-shot agent loop.

        ``scope`` carries domain-supplied focus context (e.g. which manager
        the user has selected). It is injected as a system message and
        propagated into tool inject values so the LLM stays oriented.

        ``mode`` is forwarded to ``run_chat_agent`` so that delegated
        tasks (which always pass ``mode="agent"``) match the protocol
        declared by ``AgentExecutor``.

        ``task_id`` is the supervisor task ID for this run. When set it
        is injected into the tool context so that ``ask_human`` can
        suspend the correct task.
        """
        if session_id is not None:
            return await self._ask_session(
                session_id,
                question,
                on_event=on_event,
                scope=scope,
            )

        return await self._ask_agent(
            agent_name,
            question,
            on_event=on_event,
            mode=mode,
            scope=scope,
            task_id=task_id,
        )

    async def run_chat_agent(
        self,
        agent_name: str,
        thread: list[Any],
        on_event: EventCallback | None = None,
        *,
        sandbox_session_id: str | None = None,
        mode: Literal["ask", "agent"] = "agent",
        provider: str | None = None,
        model: str | None = None,
        scope: ScopeContext | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Low-level: execute an agent over an explicit message thread."""
        config_dict, _runtime_cfg = self._load_agent_config(agent_name)
        config_dict["name"] = agent_name
        run_id = new_run_id()

        log = logger.bind(run_id=run_id, agent=agent_name, mode=mode)
        log.info("agent_run_start", thread_length=len(thread), provider=provider, model=model)

        needs_sandbox = _agent_needs_sandbox(config_dict)
        sid: str | None = (sandbox_session_id or f"chat-{run_id}") if needs_sandbox else None
        if sid:
            await self._ensure_sandbox_session(sid)

        params = RunParams(
            mode=mode,
            sandbox_session_id=sid,
            on_event=on_event,
            provider_name=provider,
            model_name=model,
        )
        ctx = self._build_context(run_id=run_id, params=params, scope=scope, extra=extra)

        thread_msgs: list[dict[str, Any]] = []
        for msg in thread:
            if isinstance(msg, ChatMessage):
                thread_msgs.append(msg.model_dump())
            elif isinstance(msg, dict):
                thread_msgs.append(msg)
            else:
                thread_msgs.append({"role": "user", "content": str(msg)})

        node = AgentNode(config=config_dict)
        output: ModuleOutput = await self._retry.execute(
            node.run,
            {"thread": thread_msgs},
            ctx,
        )

        answer = _extract_answer(output.value) or ""
        log.info(
            "agent_run_done",
            answer_length=len(answer),
            usage=output.metadata.get("usage"),
            cost=output.metadata.get("cost"),
        )
        return answer

    # -- Tier handlers -----------------------------------------------------

    async def _ask_agent(
        self,
        agent_name: str,
        question: str,
        *,
        on_event: EventCallback | None,
        mode: str = "agent",
        scope: ScopeContext | None = None,
        task_id: str | None = None,
    ) -> tuple[str | None, str]:
        """Single-shot agent loop with sandbox and tools."""
        run_id = new_run_id()
        log = logger.bind(run_id=run_id, agent=agent_name)
        log.info("ask_start", question_length=len(question))

        config_dict, _runtime_cfg = self._load_agent_config(agent_name)
        config_dict["name"] = agent_name

        # Only create a sandbox session when the agent actually declares sandbox
        # tools (bash/python). Agents that rely solely on in-process tools skip
        # session creation, workspace loading, and the destroy call entirely.
        needs_sandbox = _agent_needs_sandbox(config_dict)
        sandbox_sid: str | None = f"ask-{run_id}" if needs_sandbox else None
        if sandbox_sid:
            await self._ensure_sandbox_session(sandbox_sid)

        params = RunParams(mode=mode, sandbox_session_id=sandbox_sid, on_event=on_event)
        extra = {"task_id": task_id} if task_id else None
        ctx = self._build_context(run_id=run_id, params=params, scope=scope, extra=extra)

        try:
            node = AgentNode(config=config_dict)
            output = await self._retry.execute(node.run, {"input": question}, ctx)

            answer = _extract_answer(output.value)
            log.info(
                "ask_done",
                answer_length=len(answer) if answer else 0,
                usage=output.metadata.get("usage"),
                cost=output.metadata.get("cost"),
            )
            return (answer, run_id)
        finally:
            if sandbox_sid:
                await self._sandbox.destroy_session(sandbox_sid)

    async def _ask_session(
        self,
        session_id: str,
        question: str,
        *,
        on_event: EventCallback | None,
        scope: ScopeContext | None = None,
    ) -> tuple[str | None, str]:
        """Session-aware multi-turn — always uses the agent loop."""
        session = await self.sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        await self.sessions.append_message(
            session_id,
            ChatMessage(role="user", content=question),
        )
        refreshed = await self.sessions.get(session_id)
        thread = list(refreshed.thread) if refreshed else []

        answer = await self.run_chat_agent(
            session.agent,
            thread,
            on_event,
            sandbox_session_id=session.sandbox_session_id,
            provider=session.provider,
            model=session.model,
            scope=scope,
        )

        await self.sessions.append_message(
            session_id,
            ChatMessage(role="assistant", content=answer),
        )
        run_id = new_run_id()
        return (answer, run_id)

    # -- Internal helpers --------------------------------------------------

    def _load_agent_config(
        self,
        agent_name: str,
    ) -> tuple[dict[str, Any], RuntimeConfig]:
        """Load agent module config and runtime topology from app.yaml."""
        app_path = get_manifest_path(agent_name)
        if not app_path.exists():
            raise ValueError(f"Unknown agent: {agent_name!r} (looked in {app_path})")
        runtime_cfg = load_manifest_runtime(agent_name, manifest_path=app_path)
        with open(app_path) as f:
            data: dict[str, Any] = yaml.safe_load(f)
        for module in data.get("modules", []):
            if module.get("kind") == "agent":
                cfg: dict[str, Any] = module.get("config", {})
                return cfg, runtime_cfg
        raise ValueError(f"No agent module found in {app_path}")

    def _build_context(
        self,
        run_id: str | None = None,
        *,
        params: RunParams | None = None,
        scope: ScopeContext | None = None,
        extra: dict[str, Any] | None = None,
    ) -> RuntimeContext:
        deps = RunDeps(
            provider_factory=self._provider_factory,
            tool_registry=self._tool_registry,
            tracer=self._tracer,
            usage_ledger=self._usage_ledger,
            memory_store=self._memory_store,
            recall_service=self._recall_service,
            domain_tbox=self._domain_tbox,
            context_builder=self._context_builder,
            default_provider=self._default_provider,
            default_model=self._default_model,
        )
        merged_extras: dict[str, Any] = {"sandbox": self._sandbox}
        if self._result_schema_fn is not None:
            merged_extras["infer_result_schema"] = self._result_schema_fn
        if extra:
            merged_extras.update(extra)

        workspace = merged_extras.pop("workspace_context", None)
        if workspace is not None and not isinstance(workspace, WorkspaceContext):
            workspace = None
        if workspace is None:
            workspace = WorkspaceContext()
        merged_extras["workspace_context"] = workspace

        return RuntimeContext(
            app_id="remi",
            run_id=run_id or new_run_id(),
            deps=deps,
            params=params or RunParams(),
            scope=scope or ScopeContext(),
            workspace=workspace,
            extras=merged_extras,
        )

    async def _ensure_sandbox_session(self, session_id: str) -> None:
        session = await self._sandbox.get_session(session_id)
        if session is None:
            await self._sandbox.create_session(session_id)


_SANDBOX_TOOL_NAMES: frozenset[str] = frozenset({"bash", "python", "sandbox_exec_shell", "sandbox_exec_python"})


def _agent_needs_sandbox(config_dict: dict[str, Any]) -> bool:
    """Return True if any declared tool requires a sandbox subprocess."""
    for tool in config_dict.get("tools", []):
        name = tool if isinstance(tool, str) else (tool.get("name", "") if isinstance(tool, dict) else "")
        if name in _SANDBOX_TOOL_NAMES:
            return True
    return False


async def _noop_event(_type: str, _data: dict[str, Any]) -> None:
    pass


def _extract_answer(output: Any) -> str | None:
    """Pull the last assistant message from an agent output."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        for msg in reversed(output):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content: str | None = msg.get("content", "")
                return content
        return json.dumps(output, default=str)
    if output is not None:
        return json.dumps(output, default=str)
    return None
