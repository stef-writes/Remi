"""Base module contract — the plugin interface every module must implement."""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from remi.agent.context import RuntimeContext
from remi.models.chat import Message

__all__ = [
    "BaseModule",
    "Message",
    "ModuleDescription",
    "ModuleOutput",
    "SemanticContract",
]


class SemanticContract(BaseModel, frozen=True):
    """Structured output contract that makes module outputs LLM-legible.

    Replaces bare string labels with a schema-carrying descriptor that agents
    can reason about at graph-build time and runtime.
    """

    name: str
    description: str = ""
    output_schema: dict[str, Any] = Field(default_factory=dict)
    semantic_tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"

    @classmethod
    def from_string(cls, label: str) -> SemanticContract:
        """Backward-compat: promote a bare string label to a minimal contract."""
        return cls(name=label)

    def matches(self, other: str | SemanticContract) -> bool:
        """Check if this contract matches a name string or another contract."""
        if isinstance(other, str):
            return self.name == other
        return self.name == other.name

    def to_llm_description(self) -> str:
        """Render a human/LLM-readable summary for agent context injection."""
        parts = [f"contract:{self.name}"]
        if self.description:
            parts.append(f"  {self.description}")
        if self.output_schema:
            parts.append(f"  schema: {self.output_schema}")
        if self.semantic_tags:
            parts.append(f"  tags: {', '.join(self.semantic_tags)}")
        return "\n".join(parts)


class ModuleOutput(BaseModel):
    """Typed output produced by a module run."""

    value: Any
    contract: str | SemanticContract | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    entity_scope: str | None = None
    produced_at: datetime | None = None

    @property
    def contract_name(self) -> str | None:
        """Resolve the contract label regardless of type."""
        if self.contract is None:
            return None
        if isinstance(self.contract, SemanticContract):
            return self.contract.name
        return self.contract

    @property
    def semantic_contract(self) -> SemanticContract | None:
        """Always return a SemanticContract (promoting strings if needed)."""
        if self.contract is None:
            return None
        if isinstance(self.contract, SemanticContract):
            return self.contract
        return SemanticContract.from_string(self.contract)


class ModuleDescription(BaseModel, frozen=True):
    """Introspection metadata returned by BaseModule.describe()."""

    kind: str
    config_keys: list[str] = Field(default_factory=list)


class BaseModule(abc.ABC):
    """Abstract base class that all modules must implement.

    Subclasses set `kind` as a class attribute and implement `run()`.
    The registry maps kind strings to these classes for dynamic instantiation.
    """

    kind: str = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abc.abstractmethod
    async def run(
        self,
        inputs: dict[str, Any],
        context: RuntimeContext,
    ) -> ModuleOutput:
        """Execute the module's logic, returning a typed output."""
        ...

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Optional input validation. Returns a list of error messages."""
        return []

    def describe(self) -> ModuleDescription:
        """Introspection metadata about this module."""
        return ModuleDescription(
            kind=self.kind,
            config_keys=list(self.config.keys()),
        )
