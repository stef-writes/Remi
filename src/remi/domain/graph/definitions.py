"""Core graph definitions — pure domain objects with no I/O dependencies."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from remi.shared.ids import AppId, EdgeId, ModuleId


class ModuleDefinition(BaseModel, frozen=True):
    """Declarative description of a single module node in an app graph."""

    id: ModuleId
    kind: str
    version: str = "1.0.0"
    config: dict[str, Any] = Field(default_factory=dict)
    input_contract: str | None = None
    output_contract: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)
    description: str | None = None

    def to_llm_description(self) -> str:
        """Render a human/LLM-readable summary for agent planning."""
        parts = [f"module:{self.id} (kind={self.kind})"]
        if self.description:
            parts.append(f"  {self.description}")
        if self.input_schema:
            parts.append(f"  inputs: {self.input_schema}")
        if self.output_schema:
            parts.append(f"  outputs: {self.output_schema}")
        if self.capabilities:
            parts.append(f"  capabilities: {', '.join(self.capabilities)}")
        if self.semantic_tags:
            parts.append(f"  semantic_tags: {', '.join(self.semantic_tags)}")
        return "\n".join(parts)


class EdgeDefinition(BaseModel, frozen=True):
    """A directed edge in the app graph (source -> target)."""

    id: EdgeId | None = None
    from_module: ModuleId
    to_module: ModuleId
    condition: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.id is None:
            object.__setattr__(self, "id", EdgeId(f"{self.from_module}->{self.to_module}"))


class AppSettings(BaseModel, frozen=True):
    execution_mode: str = "full"
    state_store: str = "in_memory"
    entrypoints: list[ModuleId] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    planner_module: ModuleId | None = None


class AppMetadata(BaseModel, frozen=True):
    app_id: AppId
    name: str
    version: str = "1.0.0"
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    domain: str | None = None

    def to_llm_description(self) -> str:
        """Render a human/LLM-readable app summary for orchestrator agents."""
        parts = [f"app:{self.app_id} — {self.name} v{self.version}"]
        if self.description:
            parts.append(f"  {self.description}")
        if self.domain:
            parts.append(f"  domain: {self.domain}")
        if self.input_schema:
            parts.append(f"  accepts: {self.input_schema}")
        if self.output_schema:
            parts.append(f"  produces: {self.output_schema}")
        if self.semantic_tags:
            parts.append(f"  tags: {', '.join(self.semantic_tags)}")
        return "\n".join(parts)


class AppDefinition(BaseModel, frozen=True):
    """Complete declarative definition of an app graph."""

    api_version: str = "remi/v1"
    kind: str = "App"
    metadata: AppMetadata
    settings: AppSettings = Field(default_factory=AppSettings)
    modules: list[ModuleDefinition] = Field(default_factory=list)
    edges: list[EdgeDefinition] = Field(default_factory=list)

    @property
    def app_id(self) -> AppId:
        return self.metadata.app_id

    @property
    def module_ids(self) -> list[ModuleId]:
        return [m.id for m in self.modules]

    def get_module(self, module_id: ModuleId) -> ModuleDefinition | None:
        return next((m for m in self.modules if m.id == module_id), None)

    def get_upstream_ids(self, module_id: ModuleId) -> list[ModuleId]:
        return [e.from_module for e in self.edges if e.to_module == module_id]

    def get_downstream_ids(self, module_id: ModuleId) -> list[ModuleId]:
        return [e.to_module for e in self.edges if e.from_module == module_id]

    def to_llm_description(self) -> str:
        """Full app description for agent reasoning."""
        parts = [self.metadata.to_llm_description(), "", "Modules:"]
        for m in self.modules:
            parts.append(m.to_llm_description())
        return "\n".join(parts)
