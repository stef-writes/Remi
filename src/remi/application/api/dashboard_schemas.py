"""Dashboard API response schemas.

Re-exports from the service module — the service owns the canonical models.
"""

from __future__ import annotations

from pydantic import BaseModel

from remi.application.services.queries import (  # noqa: F401
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
from remi.application.services.monitoring.snapshots.rollups import ManagerSnapshot, PropertySnapshot

__all__ = [
    "AutoAssignResponse",
    "CaptureResponse",
    "DelinquencyBoard",
    "DelinquentTenant",
    "ExpiringLease",
    "LeaseCalendar",
    "ManagerOverview",
    "MetricsHistoryResponse",
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
    snapshots: list[ManagerSnapshot]


class CaptureResponse(BaseModel, frozen=True):
    captured: int


class MetricsHistoryResponse(BaseModel, frozen=True):
    entity_type: str
    total: int
    snapshots: list[ManagerSnapshot | PropertySnapshot]


class AutoAssignResponse(BaseModel, frozen=True):
    assigned: int
    unresolved: int
    tags_available: int
    message: str
