"""Agent delegation tool — enables orchestrator agents to invoke specialists.

The ``delegate_to_agent`` tool gives a parent agent the ability to dispatch
work to any named agent in the workforce. The specialist runs a complete
agent loop (with its own tools, sandbox session, and iteration budget)
and returns its output to the parent.

This is the core primitive for multi-agent orchestration: the director
doesn't need to *be* every agent — it invokes them.
"""

from __future__ import annotations

from typing import Any, Protocol

import structlog

from remi.agent.types import ToolArg, ToolDefinition, ToolRegistry

logger = structlog.get_logger("remi.agent.tools.delegation")


class AgentInvoker(Protocol):
    """Minimal interface for invoking an agent by name."""

    async def ask(
        self,
        agent_name: str,
        question: str,
        *,
        mode: str,
    ) -> tuple[str | None, str]: ...


def register_delegation_tools(
    registry: ToolRegistry,
    *,
    agent_invoker: AgentInvoker | None = None,
    available_agents: dict[str, str] | None = None,
) -> None:
    """Register the ``delegate_to_agent`` tool.

    *available_agents* maps agent name → description. Supplied by the
    domain profile; when empty, the tool is not registered.

    Only registered when both an ``agent_invoker`` and at least one
    available agent are provided.
    """
    if agent_invoker is None:
        return
    agents = available_agents or {}
    if not agents:
        return

    _invoker = agent_invoker

    async def delegate_to_agent(args: dict[str, Any]) -> Any:
        agent_name = args.get("agent_name", "")
        task = args.get("task", "")
        context = args.get("context", "")

        if not agent_name:
            return {"error": "agent_name is required"}
        if not task:
            return {"error": "task is required"}

        if agent_name not in agents:
            return {
                "error": f"Unknown agent '{agent_name}'",
                "available_agents": list(agents.keys()),
            }

        prompt = task
        if context:
            prompt = f"{task}\n\n## Context from parent agent\n{context}"

        logger.info(
            "delegate_to_agent",
            agent_name=agent_name,
            task_length=len(task),
            has_context=bool(context),
        )

        try:
            answer, run_id = await _invoker.ask(agent_name, prompt, mode="agent")
        except Exception as exc:
            logger.error(
                "delegate_to_agent_error",
                agent_name=agent_name,
                error=str(exc),
            )
            return {"error": str(exc), "agent_name": agent_name}

        return {
            "agent_name": agent_name,
            "run_id": run_id,
            "response": answer or "",
        }

    agent_descriptions = "\n".join(
        f"  - **{name}**: {desc}" for name, desc in agents.items()
    )

    registry.register(
        "delegate_to_agent",
        delegate_to_agent,
        ToolDefinition(
            name="delegate_to_agent",
            description=(
                "Delegate a task to a specialist agent. "
                "The specialist runs autonomously with its own tools and "
                "returns its output. Use this for tasks that require deep "
                "analysis, structured research, or specialized workflows.\n\n"
                f"Available agents:\n{agent_descriptions}"
            ),
            args=[
                ToolArg(
                    name="agent_name",
                    description=(
                        f"Name of the specialist agent to invoke. "
                        f"One of: {', '.join(agents.keys())}"
                    ),
                    required=True,
                ),
                ToolArg(
                    name="task",
                    description=(
                        "The task or question to delegate. Be specific — the "
                        "specialist has no context from your conversation unless "
                        "you provide it."
                    ),
                    required=True,
                ),
                ToolArg(
                    name="context",
                    description=(
                        "Optional context to pass to the specialist: relevant "
                        "data, constraints, or prior findings from your analysis."
                    ),
                ),
            ],
        ),
    )
