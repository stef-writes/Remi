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
    """Complete agent configuration — everything comes from YAML.

    ``provider`` and ``model`` are required with no defaults.
    Every agent node must explicitly declare which LLM it uses.
    """

    # LLM — required, model-agnostic
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 1024
    response_format: str = "text"

    # Prompts
    system_prompt: str = ""
    input_template: str | None = None

    # Tools
    tools: list[ToolRef] = Field(default_factory=list)

    # Memory
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    # Loop control
    max_iterations: int = 10
    stop_when: str = "no_tool_calls"

    # Output
    output_contract: str = "conversation"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        if "provider" not in data:
            raise ValueError(
                "AgentConfig requires an explicit 'provider' (e.g. 'openai', 'anthropic'). "
                "No default provider is assumed."
            )
        if "model" not in data:
            raise ValueError(
                "AgentConfig requires an explicit 'model' (e.g. 'gpt-4o', 'claude-sonnet-4-20250514'). "
                "No default model is assumed."
            )

        raw_tools = data.get("tools", [])
        tools: list[ToolRef] = []
        for t in raw_tools:
            if isinstance(t, str):
                tools.append(ToolRef(name=t))
            elif isinstance(t, dict):
                tools.append(ToolRef(**t))

        raw_memory = data.get("memory", {})
        memory = MemoryConfig(**raw_memory) if isinstance(raw_memory, dict) else MemoryConfig()

        return cls(
            provider=data["provider"],
            model=data["model"],
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 1024),
            response_format=data.get("response_format", "text"),
            system_prompt=data.get("system_prompt", ""),
            input_template=data.get("input_template"),
            tools=tools,
            memory=memory,
            max_iterations=data.get("max_iterations", 10),
            stop_when=data.get("stop_when", "no_tool_calls"),
            output_contract=data.get("output_contract", "conversation"),
        )
