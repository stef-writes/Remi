"""Pydantic config model for AgentNode — parsed from the YAML config dict."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolRef(BaseModel):
    """Reference to a tool available to this agent, with optional overrides."""

    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


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

    # LLM — optional, resolved at runtime via caller > yaml > settings
    provider: str | None = None
    model: str | None = None
    ask_provider: str | None = None
    ask_model: str | None = None
    agent_provider: str | None = None
    agent_model: str | None = None
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

    # Memory
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # Loop control
    max_iterations: int = 10
    ask_max_iterations: int | None = None
    agent_max_iterations: int | None = None
    stop_when: str = "no_tool_calls"

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
    def _parse_tool_list(cls, raw: list) -> list[ToolRef]:
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

        raw_memory = data.get("memory", {})
        memory = MemoryConfig(**raw_memory) if isinstance(raw_memory, dict) else MemoryConfig()

        return cls(
            provider=data.get("provider"),
            model=data.get("model"),
            ask_provider=data.get("ask_provider"),
            ask_model=data.get("ask_model"),
            agent_provider=data.get("agent_provider"),
            agent_model=data.get("agent_model"),
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
            memory=memory,
            max_iterations=data.get("max_iterations", 10),
            ask_max_iterations=data.get("ask_max_iterations"),
            agent_max_iterations=data.get("agent_max_iterations"),
            stop_when=data.get("stop_when", "no_tool_calls"),
            output_contract=data.get("output_contract", "conversation"),
        )
