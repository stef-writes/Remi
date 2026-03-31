"""FastAPI dependency injection — provides the DI container to route handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

    from remi.infrastructure.config.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]
