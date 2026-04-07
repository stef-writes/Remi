"""Workflow types — Pydantic node models, results, and DAG representation.

Node model hierarchy:
  ``NodeBase`` is the abstract base with id, depends_on, when, retry.
  Concrete subclasses (``LLMNode``, ``TransformNode``, etc.) carry
  kind-specific fields. ``WorkflowNode`` is the discriminated union
  used for YAML parsing and engine dispatch.

Wire model:
  Wires connect an output field on one node to an input field on
  another. The engine routes data by wires at runtime.

Execution events:
  Structured event types emitted by the engine during execution.
  Callers subscribe via ``EventCallback`` for UI updates, metrics, etc.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Tag

from remi.agent.llm.types import TokenUsage


# ---------------------------------------------------------------------------
# Wire — typed edge between nodes
# ---------------------------------------------------------------------------


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_step: str
    source_port: str
    target_step: str
    target_port: str
    optional: bool = False
    """When True, gating or skipping the source step does not cascade-gate
    this target step. The target receives an absent/null value for this port."""


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class BackoffStrategy(StrEnum):
    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class RetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_attempts: int = 3
    backoff: BackoffStrategy = BackoffStrategy.NONE
    base_delay: float = 1.0

    def delay_for(self, attempt: int) -> float:
        if self.backoff == BackoffStrategy.NONE:
            return 0.0
        if self.backoff == BackoffStrategy.LINEAR:
            return self.base_delay * attempt
        return self.base_delay * (2 ** (attempt - 1))


# ---------------------------------------------------------------------------
# Node base + concrete node kinds
# ---------------------------------------------------------------------------


def _get_node_kind(raw: Any) -> str:
    if isinstance(raw, dict):
        return raw.get("kind", "llm")
    return getattr(raw, "kind", "llm")


class NodeBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    depends_on: tuple[str, ...] = ()
    when: str = ""
    retry: RetryPolicy | None = None


class LLMNode(NodeBase):
    kind: Literal["llm"] = "llm"
    provider: str = ""
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    response_format: Literal["text", "json"] = "text"
    system_prompt: str = ""
    input_template: str = "{input}"
    output_schema: str = ""


class LLMToolsNode(NodeBase):
    kind: Literal["llm_tools"] = "llm_tools"
    provider: str = ""
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    response_format: Literal["text", "json"] = "text"
    system_prompt: str = ""
    input_template: str = "{input}"
    tools: tuple[str, ...] = ()
    max_tool_rounds: int = 3
    output_schema: str = ""


class TransformNode(NodeBase):
    kind: Literal["transform"] = "transform"
    tool: str


class ForEachNode(NodeBase):
    kind: Literal["for_each"] = "for_each"
    tool: str
    items_from: str = ""
    concurrency: int = 1
    on_error: Literal["collect", "abort"] = "collect"


class GateNode(NodeBase):
    kind: Literal["gate"] = "gate"
    condition: str = ""


WorkflowNode = Annotated[
    Annotated[LLMNode, Tag("llm")]
    | Annotated[LLMToolsNode, Tag("llm_tools")]
    | Annotated[TransformNode, Tag("transform")]
    | Annotated[ForEachNode, Tag("for_each")]
    | Annotated[GateNode, Tag("gate")],
    Discriminator(_get_node_kind),
]

StepConfig = WorkflowNode
"""Alias for backward compatibility with engine/steps imports."""


# ---------------------------------------------------------------------------
# Workflow defaults — from YAML top-level
# ---------------------------------------------------------------------------


class WorkflowDefaults(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str = ""
    model: str = ""
    max_concurrency: int = 4


# ---------------------------------------------------------------------------
# Workflow definition — the full parsed DAG
# ---------------------------------------------------------------------------


class WorkflowDef(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    defaults: WorkflowDefaults = WorkflowDefaults()
    steps: tuple[WorkflowNode, ...] = ()
    wires: tuple[Wire, ...] = ()

    def step_ids(self) -> frozenset[str]:
        return frozenset(s.id for s in self.steps)

    def get_step(self, step_id: str) -> WorkflowNode | None:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None


# ---------------------------------------------------------------------------
# Execution plan — pre-compiled from a WorkflowDef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InboundBinding:
    """One port-level data route: source step.port -> target step.port."""

    target_port: str
    source_step: str
    source_port: str
    optional: bool = False


@dataclass(frozen=True)
class ExecutionPlan:
    """A compiled, runtime-ready execution plan."""

    workflow: WorkflowDef
    order: tuple[str, ...]
    groups: tuple[tuple[str, ...], ...] = ()
    inbound: dict[str, tuple[InboundBinding, ...]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Step results
# ---------------------------------------------------------------------------

StepValue = str | list | dict
"""The output value of a completed step."""


@dataclass
class StepResult:
    """Output from a single step execution."""

    step_id: str
    value: StepValue
    usage: TokenUsage = field(default_factory=TokenUsage)
    skipped: bool = False
    gated: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    """Accumulated result from a completed workflow run."""

    steps: list[StepResult] = field(default_factory=list)
    total_usage: TokenUsage = field(default_factory=TokenUsage)

    def step(self, step_id: str) -> StepValue | None:
        for s in self.steps:
            if s.step_id == step_id:
                return s.value
        return None

    def step_result(self, step_id: str) -> StepResult | None:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None


# ---------------------------------------------------------------------------
# Step kind enum (for dispatch convenience)
# ---------------------------------------------------------------------------


class StepKind(StrEnum):
    LLM = "llm"
    LLM_TOOLS = "llm_tools"
    TRANSFORM = "transform"
    FOR_EACH = "for_each"
    GATE = "gate"


# ---------------------------------------------------------------------------
# Execution events — emitted by the engine during workflow runs
# ---------------------------------------------------------------------------


class NodeEvent(BaseModel):
    workflow: str
    node_id: str
    timestamp: float = 0.0

    def __init__(self, **data: Any) -> None:
        if "timestamp" not in data:
            data["timestamp"] = time.time()
        super().__init__(**data)


class NodeStarted(NodeEvent):
    kind: str = ""


class NodeCompleted(NodeEvent):
    usage: TokenUsage = TokenUsage()


class NodeSkipped(NodeEvent):
    reason: Literal["when", "gate", "explicit"] = "explicit"


class NodeRetrying(NodeEvent):
    attempt: int
    error: str


class NodeFailed(NodeEvent):
    error: str
    attempt: int = 1


EventCallback = Callable[[NodeEvent], Any]
"""Sync or async callable that receives execution events."""


# ---------------------------------------------------------------------------
# Output schema registry
# ---------------------------------------------------------------------------

OutputSchemaRegistry = dict[str, type[BaseModel]]
"""Maps schema names (from YAML ``output_schema``) to Pydantic models."""
