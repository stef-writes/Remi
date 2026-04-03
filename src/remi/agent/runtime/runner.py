"""ChatAgentService — run agents in single-shot or multi-turn chat.

Supports two execution modes:

  Single-node (kind: Agent, single module):
    ``ask`` / ``run_chat_agent`` run one AgentNode directly.

  Graph (kind: Agent, multiple modules + edges):
    ``ask`` walks the module graph in topological order.  Each module's
    ``ModuleOutput.value`` is forwarded to downstream modules as their
    ``input``.  The final node's output is returned as the answer.

    Module kinds supported in YAML:
      - ``input``  — InputModule, pass-through entry point
      - ``agent``  — AgentNode, full LLM loop
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Literal, Protocol

import structlog
import yaml

from remi.agent.config import AgentConfig
from remi.agent.context.builder import ContextBuilder
from remi.agent.runtime.base import InputModule, Message, ModuleOutput
from remi.agent.runtime.deps import RunDeps, RunParams, RuntimeContext
from remi.agent.runtime.node import AgentNode
from remi.agent.runtime.retry import RetryPolicy
from remi.agent.types import ChatSessionStore, ToolRegistry
from remi.agent.graph.stores import MemoryStore
from remi.agent.llm.factory import LLMProviderFactory
from remi.agent.observe.types import Tracer
from remi.agent.observe.usage import LLMUsageLedger
from remi.agent.sandbox.types import Sandbox
from remi.agent.signals import DomainTBox, SignalStore
from remi.types.ids import new_run_id
from remi.types.paths import AGENTS_DIR

logger = structlog.get_logger("remi.runner")


class EventCallback(Protocol):
    async def __call__(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None: ...


class ChatAgentService:
    """Runs any named agent for single-shot /ask and multi-turn chat."""

    def __init__(
        self,
        provider_factory: LLMProviderFactory,
        tool_registry: ToolRegistry,
        sandbox: Sandbox,
        domain_tbox: DomainTBox,
        signal_store: SignalStore,
        memory_store: MemoryStore,
        tracer: Tracer,
        chat_session_store: ChatSessionStore,
        retry_policy: RetryPolicy,
        default_provider: str,
        default_model: str,
        context_builder: ContextBuilder | None = None,
        usage_ledger: LLMUsageLedger | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._tool_registry = tool_registry
        self._sandbox = sandbox
        self._domain_tbox = domain_tbox
        self._signal_store = signal_store
        self._memory_store = memory_store
        self._tracer = tracer
        self._chat_session_store = chat_session_store
        self._retry = retry_policy
        self._default_provider = default_provider
        self._default_model = default_model
        self._context_builder = context_builder
        self._usage_ledger = usage_ledger

    def _load_app_yaml(self, agent_name: str) -> dict[str, Any]:
        """Load and return the raw app.yaml for an agent."""
        app_path = AGENTS_DIR / agent_name / "app.yaml"
        if not app_path.exists():
            raise ValueError(f"Unknown agent: {agent_name!r} (looked in {app_path})")
        with open(app_path) as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]

    def _load_agent_config(self, agent_name: str) -> dict[str, Any]:
        """Load the first agent module config — used by run_chat_agent (single-node path)."""
        data = self._load_app_yaml(agent_name)
        for module in data.get("modules", []):
            if module.get("kind") == "agent":
                cfg: dict[str, Any] = module.get("config", {})
                return cfg
        raise ValueError(f"No agent module found in domain/agents/{agent_name}/app.yaml")

    def _is_graph(self, data: dict[str, Any]) -> bool:
        """True when the YAML declares more than one module (i.e. a graph)."""
        return len(data.get("modules", [])) > 1

    def _topo_order(
        self,
        modules: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> list[str]:
        """Return module ids in topological execution order via Kahn's algorithm."""
        in_degree: dict[str, int] = {m["id"]: 0 for m in modules}
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            src, dst = edge["from"], edge["to"]
            adjacency[src].append(dst)
            in_degree[dst] = in_degree.get(dst, 0) + 1

        queue: deque[str] = deque(
            mid for mid, deg in in_degree.items() if deg == 0
        )
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for downstream in adjacency[node_id]:
                in_degree[downstream] -= 1
                if in_degree[downstream] == 0:
                    queue.append(downstream)

        if len(order) != len(modules):
            raise ValueError("Cycle detected in agent graph")
        return order

    async def _run_graph(
        self,
        agent_name: str,
        data: dict[str, Any],
        initial_input: str,
        context: RuntimeContext,
    ) -> ModuleOutput:
        """Execute the module graph in topological order.

        Each module receives the accumulated outputs of all its upstream
        predecessors merged into its ``inputs`` dict under the key ``input``.
        The last module's ``ModuleOutput`` is returned.
        """
        modules_by_id: dict[str, dict[str, Any]] = {
            m["id"]: m for m in data.get("modules", [])
        }
        edges: list[dict[str, Any]] = data.get("edges", [])
        order = self._topo_order(list(modules_by_id.values()), edges)

        # predecessors[node_id] = list of node_ids whose output feeds it
        predecessors: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            predecessors[edge["to"]].append(edge["from"])

        outputs: dict[str, ModuleOutput] = {}
        last_output: ModuleOutput = ModuleOutput(value=initial_input)

        for module_id in order:
            module_def = modules_by_id[module_id]
            kind = module_def.get("kind", "agent")
            cfg = module_def.get("config", {})
            cfg["name"] = module_id

            # Build inputs: merge all upstream outputs
            if predecessors[module_id]:
                # Use the last predecessor's value as primary input; attach
                # all predecessor outputs as context under their ids.
                upstream_values = {
                    pred_id: outputs[pred_id].value
                    for pred_id in predecessors[module_id]
                    if pred_id in outputs
                }
                primary_pred = predecessors[module_id][-1]
                primary_value = outputs[primary_pred].value
                node_inputs: dict[str, Any] = {
                    "input": primary_value,
                    "context": upstream_values,
                }
            else:
                node_inputs = {"input": initial_input}

            if kind == "input":
                module = InputModule(config=cfg)
                last_output = await module.run(node_inputs, context)
            elif kind == "agent":
                module_node = AgentNode(config=cfg)
                last_output = await self._retry.execute(
                    module_node.run, node_inputs, context
                )
            else:
                logger.warning(
                    "unknown_module_kind",
                    kind=kind,
                    module_id=module_id,
                    agent=agent_name,
                )
                last_output = ModuleOutput(value=node_inputs.get("input"))

            outputs[module_id] = last_output
            logger.info(
                "graph_module_done",
                agent=agent_name,
                module_id=module_id,
                kind=kind,
            )

        return last_output

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
            usage_ledger=self._usage_ledger,
            memory_store=self._memory_store,
            signal_store=self._signal_store,
            domain_tbox=self._domain_tbox,
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
        on_event: EventCallback | None = None,
    ) -> tuple[str | None, str]:
        """Single-shot agent invocation. Returns (answer, run_id).

        Automatically selects graph execution when the YAML declares multiple
        modules + edges, otherwise runs a single AgentNode.
        """
        data = self._load_app_yaml(agent_name)
        run_id = new_run_id()

        log = logger.bind(run_id=run_id, agent=agent_name, mode=mode, method="ask")
        log.info("ask_start", question_length=len(question), graph=self._is_graph(data))

        session_id = f"ask-{run_id}"
        await self._ensure_sandbox_session(session_id, mode=mode)

        params = RunParams(mode=mode, sandbox_session_id=session_id, on_event=on_event)
        ctx = self._build_context(run_id=run_id, params=params)

        try:
            if self._is_graph(data):
                output = await self._run_graph(agent_name, data, question, ctx)
            else:
                config_dict = self._load_agent_config(agent_name)
                config_dict["name"] = agent_name
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
            await self._sandbox.destroy_session(session_id)

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
                content: str | None = msg.get("content", "")
                return content
        return json.dumps(output, default=str)
    if output is not None:
        return json.dumps(output, default=str)
    return None
