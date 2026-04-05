"""Dashboard API response schemas.

Re-exports from the portfolio module — the resolver owns the canonical models.
"""

from __future__ import annotations

from pydantic import BaseModel

from remi.application.portfolio import (  # noqa: F401
    DelinquencyBoard,
    DelinquentTenant,
    ExpiringLease,
    LeaseCalendar,
    ManagerOverview,
    NeedsManagerResult,
    PortfolioOverview,
    RentRollUnit,
    RentRollView,
    UnassignedProperty,
    VacancyTracker,
    VacantUnit,
)

__all__ = [
    "AutoAssignResponse",
    "DelinquencyBoard",
    "DelinquentTenant",
    "ExpiringLease",
    "LeaseCalendar",
    "ManagerOverview",
    "NeedsManagerResult",
    "PortfolioOverview",
    "RentRollUnit",
    "RentRollView",
    "UnassignedProperty",
    "VacancyTracker",
    "VacantUnit",
]


class AutoAssignResponse(BaseModel, frozen=True):
    assigned: int
    unresolved: int
    tags_available: int
    message: str
