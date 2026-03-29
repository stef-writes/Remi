"""Result monad for explicit error handling without exceptions in domain logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> None:
        raise RuntimeError("Called unwrap_err on Ok")


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True

    def unwrap(self) -> None:
        raise RuntimeError(f"Called unwrap on Err: {self.error}")

    def unwrap_err(self) -> E:
        return self.error


Result = Union[Ok[T], Err[E]]
