"""Agent configuration — YAML manifest config models.

``AgentConfig`` and related models (``ToolRef``, ``PhaseConfig``,
``DelegateRef``, ``MemoryConfig``) are parsed from agent YAML manifests
and consumed by ``AgentNode`` in ``runtime/``.

Infrastructure settings have moved to the subsystems that own them:
- ``SecretsSettings``, ``LLMSettings`` → ``agent.llm.types``
- ``SandboxSettings`` → ``agent.sandbox.types``
- ``EmbeddingsSettings``, ``VectorStoreSettings`` → ``agent.vectors.types``
- ``MemoryStoreSettings`` → ``agent.memory.factory``
- ``TraceStoreSettings`` → ``agent.observe.factory``
- ``SessionStoreSettings`` → ``agent.sessions.factory``
- ``EventBusSettings`` → ``agent.events.factory``
- ``TaskQueueSettings`` → ``agent.tasks.factory``
- ``KernelSettings`` → ``agent.serve.kernel``
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AgentConfig",
    "ToolRef",
    "PhaseConfig",
    "DelegationConstraints",
    "DelegateRef",
    "MemoryConfig",
]

# ---------------------------------------------------------------------------
# Agent YAML manifest config — parsed by AgentNode
# ---------------------------------------------------------------------------


class ToolRef(BaseModel):
    """Reference to a tool available to this agent, with optional overrides."""

    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    inject: dict[str, str] = Field(default_factory=dict)


class PhaseConfig(BaseModel):
    """Defines a named phase in a multi-phase agent run."""

    name: str
    description: str = ""
    max_iterations: int = 5
    nudge: str = ""
    tools: list[str] = Field(default_factory=list)


class DelegationConstraints(BaseModel):
    """Resource budget for a delegation edge, declared in YAML."""

    model_config = ConfigDict(frozen=True)

    timeout_seconds: float | None = None
    max_tool_rounds: int | None = None
    max_tokens: int | None = None
    allowed_tools: list[str] | None = None


class DelegateRef(BaseModel):
    """Declarative delegation edge — this agent can spawn the target."""

    model_config = ConfigDict(frozen=True)

    agent: str
    description: str = ""
    constraints: DelegationConstraints = Field(default_factory=DelegationConstraints)


class MemoryConfig(BaseModel):
    """Memory settings for an agent node."""

    namespace: str = ""
    auto_load: bool = False
    auto_save: bool = False


class AgentConfig(BaseModel):
    """Complete agent configuration — parsed from YAML config dict."""

    name: str = "unknown"

    provider: str | None = None
    model: str | None = None
    tool_routing_provider: str | None = None
    tool_routing_model: str | None = None
    compaction_model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024
    response_format: str = "text"

    system_prompt: str = ""
    input_template: str | None = None

    tools: list[ToolRef] = Field(default_factory=list)

    delegates_to: list[DelegateRef] = Field(default_factory=list)

    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    max_iterations: int = 10
    max_history_turns: int = 10
    stop_when: str = "no_tool_calls"

    phases: list[PhaseConfig] = Field(default_factory=list)

    skills_paths: list[str] = Field(default_factory=list)

    output_contract: str = "conversation"

    @classmethod
    def _parse_tool_list(cls, raw: list[Any]) -> list[ToolRef]:
        tools: list[ToolRef] = []
        for t in raw:
            if isinstance(t, str):
                tools.append(ToolRef(name=t))
            elif isinstance(t, dict):
                tools.append(ToolRef(**t))
        return tools

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        tools = cls._parse_tool_list(data.get("tools", []))

        raw_delegates = data.get("delegates_to", [])
        delegates: list[DelegateRef] = []
        for d in raw_delegates:
            if isinstance(d, str):
                delegates.append(DelegateRef(agent=d))
            elif isinstance(d, dict):
                delegates.append(DelegateRef(**d))

        raw_memory = data.get("memory", {})
        memory = MemoryConfig(**raw_memory) if isinstance(raw_memory, dict) else MemoryConfig()

        raw_phases = data.get("phases", [])
        phases: list[PhaseConfig] = []
        for p in raw_phases:
            if isinstance(p, dict):
                phases.append(PhaseConfig(**p))

        return cls(
            name=data.get("name", "unknown"),
            provider=data.get("provider"),
            model=data.get("model"),
            tool_routing_provider=data.get("tool_routing_provider"),
            tool_routing_model=data.get("tool_routing_model"),
            compaction_model=data.get("compaction_model"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 1024),
            response_format=data.get("response_format", "text"),
            system_prompt=data.get("system_prompt", ""),
            input_template=data.get("input_template"),
            tools=tools,
            delegates_to=delegates,
            memory=memory,
            phases=phases,
            skills_paths=data.get("skills_paths", []),
            max_iterations=data.get("max_iterations", 10),
            max_history_turns=data.get("max_history_turns", 10),
            stop_when=data.get("stop_when", "no_tool_calls"),
            output_contract=data.get("output_contract", "conversation"),
        )
