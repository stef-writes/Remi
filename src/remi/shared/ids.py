"""Typed identifiers for domain entities."""

from __future__ import annotations

import uuid
from typing import NewType

AppId = NewType("AppId", str)
ModuleId = NewType("ModuleId", str)
RunId = NewType("RunId", str)
EdgeId = NewType("EdgeId", str)
ActorId = NewType("ActorId", str)


def new_run_id() -> RunId:
    return RunId(f"run-{uuid.uuid4().hex[:12]}")


def new_edge_id(source: ModuleId, target: ModuleId) -> EdgeId:
    return EdgeId(f"{source}->{target}")
