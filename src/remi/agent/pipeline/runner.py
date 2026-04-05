"""pipeline/runner.py — standalone LLM pipeline runner for document ingestion.

Reads a pipeline YAML from ``configs/<name>/app.yaml``, executes each step
in declared order by calling ``LLMProvider`` directly — no chat runtime, no
sandbox session, no context injection, no memory management.

Callable from:
  - ``IngestionService`` (API upload path)
  - ``remi documents ingest <file>`` (CLI / bash)
  - ``ingest_document`` tool (agent-triggered ingestion)
  - Future: email listener, webhook, scheduled job

Pipeline YAML shape (``kind: Pipeline``)::

    apiVersion: remi/v1
    kind: Pipeline

    steps:
      - id: classify
        model: claude-haiku-4-5-20251001
        provider: anthropic
        temperature: 0.0
        max_tokens: 1024
        response_format: json
        system_prompt: |
          ...
        input_template: |
          {input}

      - id: extract
        ...
        input_template: |
          Classification: {steps.classify}
          Document: {input}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog
import yaml

from remi.agent.llm.factory import LLMProviderFactory
from remi.agent.llm.types import Message, TokenUsage, estimate_cost
from remi.agent.observe.usage import LLMUsageLedger, UsageRecord, UsageSource
from remi.types.paths import AGENTS_DIR

_log = structlog.get_logger(__name__)

_STEP_REF_RE = re.compile(r"\{steps\.(\w+)\}")


# ---------------------------------------------------------------------------
# Pipeline step config — typed over raw YAML
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineStep:
    """A single resolved step from a pipeline YAML."""

    id: str
    provider: str
    model: str
    temperature: float
    max_tokens: int
    response_format: str
    system_prompt: str
    input_template: str

    @classmethod
    def from_raw(cls, raw: object, defaults: StepDefaults) -> PipelineStep:
        if not isinstance(raw, dict):
            raise TypeError(f"Pipeline step must be a mapping, got {type(raw).__name__}")
        return cls(
            id=str(raw.get("id", "")),
            provider=str(raw.get("provider") or defaults.provider),
            model=str(raw.get("model") or defaults.model),
            temperature=float(raw.get("temperature", 0.0)),
            max_tokens=int(raw.get("max_tokens", 4096)),
            response_format=str(raw.get("response_format", "text")),
            system_prompt=str(raw.get("system_prompt", "")),
            input_template=str(raw.get("input_template", "{input}")),
        )


@dataclass(frozen=True)
class StepDefaults:
    provider: str
    model: str


# ---------------------------------------------------------------------------
# Pipeline output types
# ---------------------------------------------------------------------------


@dataclass
class PipelineStepResult:
    """Output from a single pipeline step."""

    step_id: str
    value: str | list | dict
    usage: TokenUsage


@dataclass
class PipelineResult:
    """Accumulated result from a completed pipeline run."""

    steps: list[PipelineStepResult] = field(default_factory=list)
    total_usage: TokenUsage = field(default_factory=TokenUsage)

    def step(self, step_id: str) -> str | list | dict | None:
        """Return the parsed output of a named step, or None."""
        for s in self.steps:
            if s.step_id == step_id:
                return s.value
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_CONTEXT_REF_RE = re.compile(r"\{context\.(\w+)\}")


def _resolve_template(
    template: str,
    pipeline_input: str,
    step_outputs: dict[str, str | list | dict],
    context: dict[str, str] | None = None,
) -> str:
    """Resolve ``{input}``, ``{steps.<id>}``, and ``{context.<key>}``."""
    result = template.replace("{input}", pipeline_input)
    for match in _STEP_REF_RE.finditer(template):
        step_id = match.group(1)
        value = step_outputs.get(step_id, "")
        serialized = value if isinstance(value, str) else json.dumps(value, default=str)
        result = result.replace(match.group(0), serialized)
    if context:
        for match in _CONTEXT_REF_RE.finditer(result):
            key = match.group(1)
            result = result.replace(match.group(0), context.get(key, ""))
    return result


def _parse_json_output(raw: str) -> str | list | dict:
    """Best-effort JSON extraction — strips markdown fences if present."""
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)```$", text)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return parsed
        return text
    except (json.JSONDecodeError, TypeError):
        return text


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class IngestionPipelineRunner:
    """Runs a named pipeline YAML against LLMProvider directly.

    Steps execute sequentially in YAML order.  Each step receives ``{input}``
    (the original pipeline input) and ``{steps.<id>}`` references to all
    prior step outputs via its ``input_template``.

    No chat runtime infrastructure is involved — just LLMProvider.complete().
    """

    def __init__(
        self,
        provider_factory: LLMProviderFactory,
        default_provider: str,
        default_model: str,
        usage_ledger: LLMUsageLedger | None = None,
    ) -> None:
        self._factory = provider_factory
        self._defaults = StepDefaults(provider=default_provider, model=default_model)
        self._usage_ledger = usage_ledger

    def _load_steps(self, pipeline_name: str) -> list[PipelineStep]:
        path = AGENTS_DIR / pipeline_name / "app.yaml"
        if not path.exists():
            raise ValueError(f"No pipeline config found at {path}")
        with open(path) as f:
            data = yaml.safe_load(f)

        raw_steps: list[object] = data.get("steps") or []
        if not raw_steps:
            raise ValueError(f"Pipeline '{pipeline_name}' has no steps in {path}")
        return [PipelineStep.from_raw(s, self._defaults) for s in raw_steps]

    async def run(
        self,
        pipeline_name: str,
        pipeline_input: str,
        *,
        context: dict[str, str] | None = None,
        skip_steps: set[str] | None = None,
    ) -> PipelineResult:
        """Execute the named pipeline and return the accumulated result.

        *context*: optional string-valued dict resolved as ``{context.<key>}``
        in both system prompts and input templates — lets callers inject
        domain-specific content without the runner knowing what it is.

        *skip_steps*: optional set of step IDs to skip (no LLM call, empty
        output). Use when a step's precondition is not met (e.g. no
        unknown_rows for the enrich step).
        """
        steps = self._load_steps(pipeline_name)
        step_outputs: dict[str, str | list | dict] = {}
        result = PipelineResult()
        skip = skip_steps or set()

        _log.info(
            "pipeline_start",
            pipeline=pipeline_name,
            step_count=len(steps),
            skipped=list(skip) if skip else [],
            input_length=len(pipeline_input),
        )

        for step in steps:
            if step.id in skip:
                step_outputs[step.id] = {}
                _log.info("pipeline_step_skipped", pipeline=pipeline_name, step=step.id)
                continue

            step_result = await self._run_step(step, pipeline_input, step_outputs, context)
            step_outputs[step.id] = step_result.value
            result.steps.append(step_result)
            result.total_usage = result.total_usage + step_result.usage

            _log.info(
                "pipeline_step_done",
                pipeline=pipeline_name,
                step=step.id,
                prompt_tokens=step_result.usage.prompt_tokens,
                completion_tokens=step_result.usage.completion_tokens,
            )

        _log.info(
            "pipeline_done",
            pipeline=pipeline_name,
            total_prompt_tokens=result.total_usage.prompt_tokens,
            total_completion_tokens=result.total_usage.completion_tokens,
        )
        return result

    async def _run_step(
        self,
        step: PipelineStep,
        pipeline_input: str,
        step_outputs: dict[str, str | list | dict],
        context: dict[str, str] | None = None,
    ) -> PipelineStepResult:
        user_content = _resolve_template(
            step.input_template, pipeline_input, step_outputs, context,
        )

        messages: list[Message] = []
        if step.system_prompt:
            resolved_system = _resolve_template(
                step.system_prompt, pipeline_input, step_outputs, context,
            )
            messages.append(Message(role="system", content=resolved_system))
        messages.append(Message(role="user", content=user_content))

        provider = self._factory.create(step.provider)
        response = await provider.complete(
            model=step.model,
            messages=messages,
            temperature=step.temperature,
            max_tokens=step.max_tokens,
        )

        raw = response.content or ""
        value: str | list | dict = (
            _parse_json_output(raw) if step.response_format == "json" else raw
        )

        if self._usage_ledger is not None and response.usage.total_tokens > 0:
            cost = estimate_cost(
                step.model, response.usage.prompt_tokens, response.usage.completion_tokens,
            )
            self._usage_ledger.record(UsageRecord(
                source=UsageSource.INGESTION,
                source_detail=step.id,
                provider=step.provider,
                model=step.model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cache_read_tokens=response.usage.cache_read_tokens,
                cache_creation_tokens=response.usage.cache_creation_tokens,
                estimated_cost_usd=round(cost, 6) if cost is not None else None,
            ))

        return PipelineStepResult(step_id=step.id, value=value, usage=response.usage)
