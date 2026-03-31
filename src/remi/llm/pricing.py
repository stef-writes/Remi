"""LLM model pricing — per-million-token rates for cost estimation.

Keep this in sync with the frontend pricing table in SessionThread.tsx.
Rates sourced from provider pricing pages as of 2026-03.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token pricing for a single model."""

    input_per_1m: float
    output_per_1m: float


PRICING: dict[str, ModelPricing] = {
    # Anthropic
    "claude-opus-4-20250514": ModelPricing(5.0, 25.0),
    "claude-opus-4-6": ModelPricing(5.0, 25.0),
    "claude-sonnet-4-20250514": ModelPricing(3.0, 15.0),
    "claude-sonnet-4-6": ModelPricing(3.0, 15.0),
    "claude-sonnet-4-5-20250929": ModelPricing(3.0, 15.0),
    "claude-haiku-4-5-20251001": ModelPricing(1.0, 5.0),
    # OpenAI
    "gpt-4o": ModelPricing(2.5, 10.0),
    "gpt-4o-mini": ModelPricing(0.15, 0.6),
    "gpt-4-turbo": ModelPricing(10.0, 30.0),
    # Google
    "gemini-2.0-flash": ModelPricing(0.1, 0.4),
    "gemini-1.5-pro": ModelPricing(1.25, 5.0),
}


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """Return estimated cost in USD, or None if model pricing is unknown."""
    pricing = PRICING.get(model)
    if pricing is None:
        return None
    return (
        prompt_tokens * pricing.input_per_1m / 1_000_000
        + completion_tokens * pricing.output_per_1m / 1_000_000
    )
