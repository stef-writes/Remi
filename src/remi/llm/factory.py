"""LLM provider factory — runtime-agnostic provider resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from remi.llm.ports import LLMProvider


class LLMProviderFactory:
    """Creates LLM provider instances by name.

    Provider constructors are registered at startup; no provider is assumed.
    Both the Platform Agent and individual Agent Module Nodes resolve their
    provider through this factory via ``factory.create(provider_name, **kwargs)``.
    """

    def __init__(self) -> None:
        self._constructors: dict[str, Callable[..., LLMProvider]] = {}

    def register(self, name: str, constructor: Callable[..., LLMProvider]) -> None:
        self._constructors[name] = constructor

    def create(self, name: str, **kwargs: Any) -> LLMProvider:
        if name not in self._constructors:
            available = ", ".join(sorted(self._constructors)) or "(none registered)"
            raise ValueError(
                f"Unknown LLM provider '{name}'. "
                f"Available: {available}. "
                f"Install the provider package and ensure it is registered."
            )
        return self._constructors[name](**kwargs)

    def available(self) -> list[str]:
        return sorted(self._constructors)

    def has(self, name: str) -> bool:
        return name in self._constructors
