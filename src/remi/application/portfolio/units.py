"""Units — cross-property unit queries."""

from __future__ import annotations

from remi.application.core.models import UnitStatus
from remi.application.core.protocols import PropertyStore

from ._models import UnitListItem, UnitListResult


class UnitResolver:
    """Entity resolver for units."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_units(
        self,
        property_id: str | None = None,
        status: str | None = None,
    ) -> UnitListResult:
        unit_status = UnitStatus(status) if status else None
        units = await self._ps.list_units(property_id=property_id, status=unit_status)
        items: list[UnitListItem] = []
        for u in units:
            prop = await self._ps.get_property(u.property_id)
            items.append(
                UnitListItem(
                    id=u.id,
                    unit_number=u.unit_number,
                    property_name=prop.name if prop else u.property_id,
                    property_id=u.property_id,
                    status=u.status.value,
                    bedrooms=u.bedrooms,
                    sqft=u.sqft,
                    market_rent=float(u.market_rent),
                    current_rent=float(u.current_rent),
                )
            )
        return UnitListResult(count=len(items), units=items)
