"""Dashboard API response schemas.

Re-exports from the service module — the service owns the canonical models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from remi.services.dashboard import (
    DelinquencyBoard,
    DelinquentTenant,
    ExpiringLease,
    LeaseCalendar,
    ManagerOverview,
    PortfolioOverview,
    RentRollUnit,
    RentRollView,
    VacancyTracker,
    VacantUnit,
)

__all__ = [
    "AutoAssignResponse",
    "CaptureResponse",
    "DelinquencyBoard",
    "DelinquentTenant",
    "ExpiringLease",
    "LeaseCalendar",
    "ManagerOverview",
    "NeedsManagerResponse",
    "PortfolioOverview",
    "RentRollUnit",
    "RentRollView",
    "SnapshotsResponse",
    "UnassignedProperty",
    "VacancyTracker",
    "VacantUnit",
]


class UnassignedProperty(BaseModel, frozen=True):
    id: str
    name: str
    address: str


class NeedsManagerResponse(BaseModel, frozen=True):
    total: int
    properties: list[UnassignedProperty]


class SnapshotsResponse(BaseModel, frozen=True):
    total: int
    snapshots: list[dict[str, Any]]


class CaptureResponse(BaseModel, frozen=True):
    captured: int


class AutoAssignResponse(BaseModel, frozen=True):
    assigned: int
    unresolved: int
    message: str
