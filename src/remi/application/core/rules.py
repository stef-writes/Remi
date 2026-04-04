"""Pure business rule functions for portfolio entities.

Stateless, no I/O — just computations over DTOs.

Canonical unit-level classification: occupancy, vacancy, loss-to-lease,
maintenance status, and below-market classification. Every service that
needs to classify a unit (snapshots, dashboard, manager_review, rent_roll)
should use these functions so the rules stay consistent across views.
"""

from __future__ import annotations

from decimal import Decimal

from remi.application.core.models import (
    MaintenanceRequest,
    MaintenanceStatus,
    OccupancyStatus,
    Unit,
    UnitStatus,
)

BELOW_MARKET_THRESHOLD = 0.03  # 3 % gap between current and market rent


def is_occupied(unit: Unit) -> bool:
    """True when a unit should count as occupied."""
    if unit.status == UnitStatus.OCCUPIED:
        return True
    return unit.occupancy_status == OccupancyStatus.OCCUPIED


def is_vacant(unit: Unit) -> bool:
    """True when a unit should count as vacant."""
    if unit.status == UnitStatus.VACANT:
        return True
    return bool(
        unit.occupancy_status
        and unit.occupancy_status
        in (OccupancyStatus.VACANT_RENTED, OccupancyStatus.VACANT_UNRENTED)
    )


def loss_to_lease(unit: Unit) -> Decimal:
    """Per-unit loss-to-lease (zero when current >= market)."""
    if unit.current_rent < unit.market_rent:
        return unit.market_rent - unit.current_rent
    return Decimal("0")


def is_below_market(unit: Unit) -> bool:
    """True when the unit's rent gap exceeds the threshold."""
    if unit.market_rent <= 0:
        return False
    if unit.current_rent >= unit.market_rent:
        return False
    return float((unit.market_rent - unit.current_rent) / unit.market_rent) > BELOW_MARKET_THRESHOLD


def pct_below_market(unit: Unit) -> float:
    """Percentage the unit is below market (0.0 when at or above)."""
    if unit.market_rent <= 0 or unit.current_rent >= unit.market_rent:
        return 0.0
    return round(float((unit.market_rent - unit.current_rent) / unit.market_rent) * 100, 1)


def is_maintenance_open(request: MaintenanceRequest) -> bool:
    """True when a maintenance request should count as open/active."""
    return request.status in (MaintenanceStatus.OPEN, MaintenanceStatus.IN_PROGRESS)


def manager_name_from_tag(tag: str) -> str:
    """Extract and normalize the person's name from a manager tag.

    Handles tags like 'Jake Kraus Management', 'Jake  Kraus' (extra spaces),
    or bare names. Strips known company suffixes and normalizes whitespace so
    'Jake  Kraus' and 'Jake Kraus' resolve to the same manager.
    """
    suffixes = ("management", "mgmt", "properties", "property")
    name = " ".join(tag.split())
    lower = name.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            name = " ".join(name[: -len(suffix)].split())
            break
    return name or " ".join(tag.split())
