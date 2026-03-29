"""Financial metrics and time-series snapshots for the real estate domain."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MetricSnapshot(BaseModel, frozen=True):
    """A single metric observation for a property, portfolio, or manager."""

    entity_type: str
    entity_id: str
    metric_name: str
    value: Decimal
    period: str
    recorded_at: datetime = Field(default_factory=_utcnow)


class FinancialSummary(BaseModel, frozen=True):
    """Aggregated financial performance for a property or portfolio."""

    entity_type: str
    entity_id: str
    period: str
    gross_revenue: Decimal = Decimal("0")
    operating_expenses: Decimal = Decimal("0")
    maintenance_costs: Decimal = Decimal("0")
    noi: Decimal = Decimal("0")
    occupancy_rate: float = 0.0
    total_units: int = 0
    occupied_units: int = 0
    avg_rent_per_unit: Decimal = Decimal("0")
    recorded_at: datetime = Field(default_factory=_utcnow)

    @property
    def vacancy_rate(self) -> float:
        return 1.0 - self.occupancy_rate

    @property
    def loss_to_lease(self) -> Decimal:
        return self.gross_revenue - self.noi - self.operating_expenses - self.maintenance_costs
