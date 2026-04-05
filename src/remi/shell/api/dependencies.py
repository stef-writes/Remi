"""FastAPI dependency injection — Annotated type aliases.

One real function: ``get_container`` pulls the Container off ``request.app.state``.
Everything else is an ``Annotated`` alias so routers declare narrow types
without 27 wrapper functions.

Override ``get_container`` in tests to swap the whole dependency tree.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from remi.shell.config.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


Ctr = Annotated[Container, Depends(get_container)]
