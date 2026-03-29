"""Runtime context — the environment bag passed to every module during execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from remi.shared.enums import ExecutionMode
from remi.shared.ids import ActorId, AppId, RunId


@dataclass(frozen=True)
class RuntimeContext:
    """Immutable execution context threaded through all layers."""

    app_id: AppId
    run_id: RunId
    environment: str = "development"
    actor_id: ActorId | None = None
    execution_mode: ExecutionMode = ExecutionMode.FULL
    tags: dict[str, str] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    def with_extras(self, **kwargs: Any) -> RuntimeContext:
        merged = {**self.extras, **kwargs}
        return RuntimeContext(
            app_id=self.app_id,
            run_id=self.run_id,
            environment=self.environment,
            actor_id=self.actor_id,
            execution_mode=self.execution_mode,
            tags=self.tags,
            extras=merged,
        )
