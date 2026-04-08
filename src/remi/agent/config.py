"""Pydantic config model for AgentNode — parsed from the YAML config dict."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolRef(BaseModel):
    """Reference to a tool available to this agent, with optional overrides.

    ``config`` is merged into the tool arguments at resolution time — this
    is how the same tool name gets agent-specific behavior.  ``description``
    replaces the base tool description so the LLM sees an agent-tailored
    version.  ``inject`` maps argument names to well-known runtime context
    keys (e.g. ``sandbox_session_id``) that are auto-filled if not provided
    by the LLM.

    Example YAML::

        tools:
          - name: python
            description: "Persistent Python session with remi SDK."
            config:
              timeout: 120
            inject:
              session_id: sandbox_session_id
          - name: semantic_search
            config:
              default_limit: 20
              entity_types: [Unit, Lease]
    """

    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    inject: dict[str, str] = Field(default_factory=dict)


class PhaseConfig(BaseModel):
    """Defines a named phase in a multi-phase agent run.

    Used by the researcher to enforce structured progress through
    DATA -> ANALYZE -> SYNTHESIZE stages with iteration budgets.

    When *tools* is set, only the listed tool names are active during
    this phase.  Unlisted tools are stripped from the LLM request,
    saving tokens in later phases where they're dead weight.
    """

    name: str
    description: str = ""
    max_iterations: int = 5
    nudge: str = ""
    tools: list[str] = Field(default_factory=list)


class DelegationConstraints(BaseModel):
    """Resource budget for a delegation edge, declared in YAML.

    Maps 1:1 with ``TaskConstraints`` fields but lives in the config
    layer (Pydantic) rather than the task layer (dataclass). Use
    ``to_task_constraints()`` to bridge when creating a ``TaskSpec``.
    """

    model_config = ConfigDict(frozen=True)

    timeout_seconds: float | None = None
    max_tool_rounds: int | None = None
    max_tokens: int | None = None
    allowed_tools: list[str] | None = None


class DelegateRef(BaseModel):
    """Declarative delegation edge — this agent can spawn the target.

    Declared in agent YAML under ``delegates_to:``. The ``Workforce``
    model assembles these edges into a per-parent delegation graph
    that the delegation tool enforces at runtime and a canvas UI
    can render and edit.

    Example YAML::

        delegates_to:
          - agent: researcher
            description: "Deep statistical analysis and reports"
            constraints:
              timeout_seconds: 300
              max_tool_rounds: 20
          - agent: action_planner
            description: "Draft action items from manager review data"
            constraints:
              timeout_seconds: 30
    """

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
    """Complete agent configuration — parsed from YAML config dict.

    ``provider`` and ``model`` are optional. When absent, they are resolved
    at runtime from the caller (frontend selection) or settings defaults.
    YAML defines agent *behavior*; the model is a runtime choice.

    Tool surfaces are mode-aware: ``ask_tools`` for fast Q&A, ``agent_tools``
    for deep autonomous work.  A flat ``tools`` list is still supported as
    fallback (used when no mode-specific list is defined, or for non-chat
    agents like the knowledge enricher).
    """

    # Identity
    name: str = "unknown"

    # LLM — optional, resolved at runtime via caller > yaml > settings
    provider: str | None = None
    model: str | None = None
    ask_provider: str | None = None
    ask_model: str | None = None
    agent_provider: str | None = None
    agent_model: str | None = None
    tool_routing_provider: str | None = None
    tool_routing_model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024
    response_format: str = "text"

    # Prompts
    system_prompt: str = ""
    ask_system_prompt: str | None = None
    agent_system_prompt: str | None = None
    input_template: str | None = None

    # Tools — mode-aware
    tools: list[ToolRef] = Field(default_factory=list)
    ask_tools: list[ToolRef] = Field(default_factory=list)
    agent_tools: list[ToolRef] = Field(default_factory=list)

    # Delegation graph — which agents this one can spawn
    delegates_to: list[DelegateRef] = Field(default_factory=list)

    # Memory
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # Loop control
    max_iterations: int = 10
    ask_max_iterations: int | None = None
    agent_max_iterations: int | None = None
    max_history_turns: int = 10
    stop_when: str = "no_tool_calls"
    compact_tbox: bool = False

    # Phase-gated execution (researcher)
    phases: list[PhaseConfig] = Field(default_factory=list)

    # Skills — filesystem paths to discover playbook SKILL.md files
    skills_paths: list[str] = Field(default_factory=list)

    # Output
    output_contract: str = "conversation"

    def provider_for_mode(self, mode: str) -> str | None:
        """Return the provider for the given mode, falling back to the base."""
        if mode == "ask" and self.ask_provider:
            return self.ask_provider
        if mode == "agent" and self.agent_provider:
            return self.agent_provider
        return self.provider

    def model_for_mode(self, mode: str) -> str | None:
        """Return the model for the given mode, falling back to the base."""
        if mode == "ask" and self.ask_model:
            return self.ask_model
        if mode == "agent" and self.agent_model:
            return self.agent_model
        return self.model

    def tools_for_mode(self, mode: str) -> list[ToolRef]:
        """Return the tool list appropriate for the given mode."""
        if mode == "ask" and self.ask_tools:
            return self.ask_tools
        if mode == "agent" and self.agent_tools:
            return self.agent_tools
        return self.tools

    def system_prompt_for_mode(self, mode: str) -> str:
        """Return the system prompt appropriate for the given mode."""
        if mode == "ask" and self.ask_system_prompt:
            return self.ask_system_prompt
        if mode == "agent" and self.agent_system_prompt:
            return self.agent_system_prompt
        return self.system_prompt

    def max_iterations_for_mode(self, mode: str) -> int:
        if mode == "ask" and self.ask_max_iterations is not None:
            return self.ask_max_iterations
        if mode == "agent" and self.agent_max_iterations is not None:
            return self.agent_max_iterations
        return self.max_iterations

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
        ask_tools = cls._parse_tool_list(data.get("ask_tools", []))
        agent_tools = cls._parse_tool_list(data.get("agent_tools", []))

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
            ask_provider=data.get("ask_provider"),
            ask_model=data.get("ask_model"),
            agent_provider=data.get("agent_provider"),
            agent_model=data.get("agent_model"),
            tool_routing_provider=data.get("tool_routing_provider"),
            tool_routing_model=data.get("tool_routing_model"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 1024),
            response_format=data.get("response_format", "text"),
            system_prompt=data.get("system_prompt", ""),
            ask_system_prompt=data.get("ask_system_prompt"),
            agent_system_prompt=data.get("agent_system_prompt"),
            input_template=data.get("input_template"),
            tools=tools,
            ask_tools=ask_tools,
            agent_tools=agent_tools,
            delegates_to=delegates,
            memory=memory,
            phases=phases,
            skills_paths=data.get("skills_paths", []),
            max_iterations=data.get("max_iterations", 10),
            ask_max_iterations=data.get("ask_max_iterations"),
            agent_max_iterations=data.get("agent_max_iterations"),
            max_history_turns=data.get("max_history_turns", 10),
            stop_when=data.get("stop_when", "no_tool_calls"),
            compact_tbox=data.get("compact_tbox", False),
            output_contract=data.get("output_contract", "conversation"),
        )
