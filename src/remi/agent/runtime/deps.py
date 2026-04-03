"""Runtime context — typed execution environment passed to modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from remi.agent.context.builder import ContextBuilder
from remi.agent.types import ToolRegistry
from remi.agent.graph.stores import MemoryStore
from remi.agent.llm.factory import LLMProviderFactory
from remi.agent.observe.types import Tracer
from remi.agent.observe.usage import LLMUsageLedger
from remi.agent.signals import DomainTBox, SignalStore


class OnEventCallback(Protocol):
    """Typed callback for agent streaming events."""

    async def __call__(self, event_type: str, data: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class RunDeps:
    """Typed dependencies injected once per container lifetime."""

    provider_factory: LLMProviderFactory | None = None
    tool_registry: ToolRegistry | None = None
    tracer: Tracer | None = None
    usage_ledger: LLMUsageLedger | None = None
    memory_store: MemoryStore | None = None
    signal_store: SignalStore | None = None
    domain_tbox: DomainTBox | None = None
    context_builder: ContextBuilder | None = None
    default_provider: str = ""
    default_model: str = ""


@dataclass(frozen=True)
class RunParams:
    """Per-request parameters that vary between invocations."""

    mode: str = "agent"
    provider_name: str | None = None
    model_name: str | None = None
    sandbox_session_id: str | None = None
    on_event: OnEventCallback | None = None


@dataclass(frozen=True)
class RuntimeContext:
    """Immutable execution context threaded through agent runs.

    ``deps`` carries typed container-lifetime dependencies.
    ``params`` carries typed per-request parameters.
    ``extras`` remains as a narrow escape hatch for dynamic/experimental data.
    """

    app_id: str = "remi"
    run_id: str = ""
    environment: str = "development"
    deps: RunDeps = field(default_factory=RunDeps)
    params: RunParams = field(default_factory=RunParams)
    extras: dict[str, Any] = field(default_factory=dict)

    def with_extras(self, **kwargs: Any) -> RuntimeContext:
        merged = {**self.extras, **kwargs}
        return RuntimeContext(
            app_id=self.app_id,
            run_id=self.run_id,
            environment=self.environment,
            deps=self.deps,
            params=self.params,
            extras=merged,
        )
