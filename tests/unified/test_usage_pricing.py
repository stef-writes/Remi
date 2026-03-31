"""Tests for token usage aggregation and cost estimation."""

from __future__ import annotations

import pytest

from remi.llm.pricing import PRICING, ModelPricing, estimate_cost
from remi.llm.ports import TokenUsage


class TestTokenUsage:
    def test_basic_addition(self) -> None:
        a = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        b = TokenUsage(prompt_tokens=200, completion_tokens=80, total_tokens=280)
        result = a + b
        assert result.prompt_tokens == 300
        assert result.completion_tokens == 130
        assert result.total_tokens == 430

    def test_add_to_zero(self) -> None:
        zero = TokenUsage()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        result = zero + usage
        assert result == usage

    def test_from_dict(self) -> None:
        raw = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        usage = TokenUsage.from_dict(raw)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50

    def test_from_empty_dict(self) -> None:
        usage = TokenUsage.from_dict({})
        assert usage == TokenUsage()

    def test_to_dict_roundtrip(self) -> None:
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert TokenUsage.from_dict(usage.to_dict()) == usage

    def test_frozen(self) -> None:
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        with pytest.raises(Exception):
            usage.prompt_tokens = 999  # type: ignore[misc]


class TestEstimateCost:
    def test_sonnet_cost(self) -> None:
        cost = estimate_cost("claude-sonnet-4-6-20260320", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(3.0 + 15.0)

    def test_opus_cost(self) -> None:
        cost = estimate_cost("claude-opus-4-6-20260320", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(15.0 + 75.0)

    def test_unknown_model_returns_none(self) -> None:
        assert estimate_cost("unknown-model-xyz", 500, 200) is None

    def test_zero_tokens(self) -> None:
        cost = estimate_cost("claude-sonnet-4-6-20260320", 0, 0)
        assert cost is not None
        assert cost == 0.0

    def test_small_request(self) -> None:
        cost = estimate_cost("claude-sonnet-4-6-20260320", 1000, 500)
        assert cost is not None
        expected = (1000 * 3.0 / 1_000_000) + (500 * 15.0 / 1_000_000)
        assert cost == pytest.approx(expected)

    def test_all_models_have_valid_pricing(self) -> None:
        for model, pricing in PRICING.items():
            assert pricing.input_per_1m > 0, f"{model} has non-positive input pricing"
            assert pricing.output_per_1m > 0, f"{model} has non-positive output pricing"

    def test_gpt4o_cost(self) -> None:
        cost = estimate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost is not None
        assert cost == pytest.approx(2.5 + 10.0)
