"""ChatAgentService — run agents in single-shot or multi-turn chat.

Calls AgentNode.run() directly — no graph runtime.
Loads agent config from agents/<name>/app.yaml and builds a RuntimeContext
with typed RunDeps and RunParams.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Protocol

import structlog
import yaml

from remi.agent.base import Message, ModuleOutput
from remi.agent.context import RunDeps, RunParams, RuntimeContext
from remi.agent.node import AgentNode
from remi.agent.retry import RetryPolicy
from remi.knowledge.context_builder import ContextBuilder
from remi.llm.factory import LLMProviderFactory
from remi.models.chat import AgentEvent, ChatSessionStore
from remi.models.memory import MemoryStore
from remi.models.sandbox import Sandbox
from remi.models.signals import DomainRulebook, SignalStore
from remi.models.tools import ToolRegistry
from remi.observability.tracer import Tracer
from remi.shared.ids import new_run_id
from remi.shared.paths import AGENTS_DIR

logger = structlog.get_logger("remi.runner")


class EventCallback(Protocol):
    async def __call__(
        self,
        event_type: str,
        data: dict[str, Any] | AgentEvent,
    ) -> None: ...


class ChatAgentService:
    """Runs the director agent for single-shot /ask and multi-turn chat."""

    def __init__(
        self,
        provider_factory: LLMProviderFactory,
        tool_registry: ToolRegistry,
        sandbox: Sandbox,
        domain_rulebook: DomainRulebook,
        signal_store: SignalStore,
        memory_store: MemoryStore,
        tracer: Tracer,
        chat_session_store: ChatSessionStore,
        retry_policy: RetryPolicy,
        default_provider: str,
        default_model: str,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._tool_registry = tool_registry
        self._sandbox = sandbox
        self._domain_rulebook = domain_rulebook
        self._signal_store = signal_store
        self._memory_store = memory_store
        self._tracer = tracer
        self._chat_session_store = chat_session_store
        self._retry = retry_policy
        self._default_provider = default_provider
        self._default_model = default_model
        self._context_builder = context_builder

    def _load_agent_config(self, agent_name: str) -> dict[str, Any]:
        """Load the agent module config from its app.yaml."""
        app_path = AGENTS_DIR / agent_name / "app.yaml"
        if not app_path.exists():
            raise ValueError(f"Unknown agent: {agent_name}")

        with open(app_path) as f:
            data = yaml.safe_load(f)

        for module in data.get("modules", []):
            if module.get("kind") == "agent":
                return module.get("config", {})

        raise ValueError(f"No agent module found in {app_path}")

    def _build_context(
        self,
        run_id: str | None = None,
        *,
        params: RunParams | None = None,
        extra: dict[str, Any] | None = None,
    ) -> RuntimeContext:
        deps = RunDeps(
            provider_factory=self._provider_factory,
            tool_registry=self._tool_registry,
            tracer=self._tracer,
            memory_store=self._memory_store,
            signal_store=self._signal_store,
            domain_rulebook=self._domain_rulebook,
            context_builder=self._context_builder,
            default_provider=self._default_provider,
            default_model=self._default_model,
        )
        return RuntimeContext(
            app_id="remi",
            run_id=run_id or new_run_id(),
            deps=deps,
            params=params or RunParams(),
            extras=extra or {},
        )

    async def _ensure_sandbox_session(
        self,
        session_id: str,
        *,
        mode: Literal["ask", "agent"] = "agent",
    ) -> None:
        """Create sandbox session if it doesn't exist yet."""
        session = await self._sandbox.get_session(session_id)
        if session is None:
            await self._sandbox.create_session(
                session_id,
                extra_env={"REMI_MODE": mode},
            )

    async def ask(
        self,
        agent_name: str,
        question: str,
        *,
        mode: Literal["ask", "agent"] = "agent",
    ) -> tuple[str | None, str]:
        """Single-shot agent invocation. Returns (answer, run_id)."""
        config_dict = self._load_agent_config(agent_name)
        config_dict["name"] = agent_name
        run_id = new_run_id()

        log = logger.bind(run_id=run_id, agent=agent_name, mode=mode, method="ask")
        log.info("ask_start", question_length=len(question))

        session_id = f"ask-{run_id}"
        await self._ensure_sandbox_session(session_id, mode=mode)

        params = RunParams(mode=mode, sandbox_session_id=session_id)
        ctx = self._build_context(run_id=run_id, params=params)

        node = AgentNode(config=config_dict)
        output: ModuleOutput = await self._retry.execute(
            node.run,
            {"input": question},
            ctx,
        )

        answer = _extract_answer(output.value)
        log.info(
            "ask_done",
            answer_length=len(answer) if answer else 0,
            usage=output.metadata.get("usage"),
            cost=output.metadata.get("cost"),
        )
        return (answer, run_id)

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
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Multi-turn agent execution over a message thread."""
        config_dict = self._load_agent_config(agent_name)
        config_dict["name"] = agent_name
        run_id = new_run_id()

        log = logger.bind(run_id=run_id, agent=agent_name, mode=mode, method="chat")
        log.info("chat_run_start", thread_length=len(thread), provider=provider, model=model)

        session_id = sandbox_session_id or f"chat-{run_id}"
        await self._ensure_sandbox_session(session_id, mode=mode)

        params = RunParams(
            mode=mode,
            sandbox_session_id=session_id,
            on_event=on_event,
            provider_name=provider,
            model_name=model,
        )
        ctx = self._build_context(run_id=run_id, params=params, extra=extra)

        thread_msgs: list[dict[str, Any]] = []
        for msg in thread:
            if isinstance(msg, Message):
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
            "chat_run_done",
            answer_length=len(answer),
            iterations=output.metadata.get("iterations"),
            usage=output.metadata.get("usage"),
            cost=output.metadata.get("cost"),
        )
        return answer


def _extract_answer(output: Any) -> str | None:
    """Pull the last assistant message from an agent output."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        for msg in reversed(output):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                return msg.get("content", "")
        return json.dumps(output, default=str)
    if output is not None:
        return json.dumps(output, default=str)
    return None
