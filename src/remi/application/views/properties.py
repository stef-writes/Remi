"""Properties — list, detail, and computed fields."""

from __future__ import annotations

from decimal import Decimal

from remi.application.core.models import LeaseStatus
from remi.application.core.protocols import PropertyStore
from remi.application.core.rules import (
    active_lease,
    derive_occupancy_status,
    is_occupied,
)

from ._models import (
    PropertyDetail,
    PropertyDetailUnit,
    PropertyListItem,
    UnitListItem,
    UnitListResult,
)


class PropertyResolver:
    """Entity resolver for properties."""

    def __init__(self, property_store: PropertyStore) -> None:
        self._ps = property_store

    async def list_properties(
        self,
        *,
        manager_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[PropertyListItem]:
        properties = await self._ps.list_properties(
            manager_id=manager_id,
            owner_id=owner_id,
        )
        items: list[PropertyListItem] = []
        for p in properties:
            units = await self._ps.list_units(property_id=p.id)
            all_leases = await self._ps.list_leases(property_id=p.id)
            leases_by_unit = _group_by_unit(all_leases)
            occ = sum(1 for u in units if is_occupied(leases_by_unit.get(u.id, [])))

            o_name: str | None = None
            if p.owner_id:
                owner = await self._ps.get_owner(p.owner_id)
                if owner:
                    o_name = owner.name

            items.append(
                PropertyListItem(
                    id=p.id,
                    name=p.name,
                    address=p.address.one_line(),
                    type=p.property_type.value,
                    year_built=p.year_built,
                    total_units=len(units),
                    occupied=occ,
                    manager_id=p.manager_id,
                    owner_id=p.owner_id,
                    owner_name=o_name,
                )
            )
        return items

    async def get_property_detail(self, property_id: str) -> PropertyDetail | None:
        prop = await self._ps.get_property(property_id)
        if not prop:
            return None

        units = await self._ps.list_units(property_id=property_id)
        all_leases = await self._ps.list_leases(property_id=property_id)
        active_leases = [le for le in all_leases if le.status == LeaseStatus.ACTIVE]
        leases_by_unit = _group_by_unit(all_leases)

        occupied = sum(1 for u in units if is_occupied(leases_by_unit.get(u.id, [])))
        vacant = len(units) - occupied
        revenue = sum(
            (le.monthly_rent for le in active_leases),
            Decimal("0"),
        )

        manager_id: str | None = None
        manager_name: str | None = None
        if prop.manager_id:
            manager = await self._ps.get_manager(prop.manager_id)
            if manager:
                manager_id = manager.id
                manager_name = manager.name

        o_id: str | None = None
        o_name: str | None = None
        if prop.owner_id:
            owner = await self._ps.get_owner(prop.owner_id)
            if owner:
                o_id = owner.id
                o_name = owner.name

        unit_rows: list[PropertyDetailUnit] = []
        for u in units:
            unit_leases = leases_by_unit.get(u.id, [])
            act = active_lease(unit_leases)
            occ_status = derive_occupancy_status(unit_leases)
            unit_rows.append(
                PropertyDetailUnit(
                    id=u.id,
                    property_id=property_id,
                    unit_number=u.unit_number,
                    status="occupied" if act else "vacant",
                    occupancy_status=occ_status.value,
                    bedrooms=u.bedrooms,
                    bathrooms=u.bathrooms,
                    sqft=u.sqft,
                    floor=u.floor,
                    market_rent=float(u.market_rent),
                    current_rent=float(act.monthly_rent) if act else 0.0,
                )
            )

        return PropertyDetail(
            id=property_id,
            name=prop.name,
            address=prop.address,
            property_type=prop.property_type.value,
            year_built=prop.year_built,
            manager_id=manager_id,
            manager_name=manager_name,
            owner_id=o_id,
            owner_name=o_name,
            total_units=len(units),
            occupied=occupied,
            vacant=vacant,
            occupancy_rate=round(occupied / len(units), 3) if units else 0,
            monthly_revenue=float(revenue),
            active_leases=len(active_leases),
            units=unit_rows,
        )

    async def list_all_units(
        self,
        property_id: str | None = None,
    ) -> UnitListResult:
        """Cross-property unit listing with occupancy and current rent."""
        units = await self._ps.list_units(property_id=property_id)
        if not units:
            return UnitListResult(count=0, units=[])

        all_leases = await self._ps.list_leases(property_id=property_id)
        leases_by_unit = _group_by_unit(all_leases)

        items: list[UnitListItem] = []
        for u in units:
            prop = await self._ps.get_property(u.property_id)
            unit_leases = leases_by_unit.get(u.id, [])
            act = active_lease(unit_leases)
            items.append(
                UnitListItem(
                    id=u.id,
                    unit_number=u.unit_number,
                    property_name=prop.name if prop else u.property_id,
                    property_id=u.property_id,
                    status="occupied" if is_occupied(unit_leases) else "vacant",
                    bedrooms=u.bedrooms,
                    sqft=u.sqft,
                    market_rent=float(u.market_rent),
                    current_rent=float(act.monthly_rent) if act else 0.0,
                )
            )
        return UnitListResult(count=len(items), units=items)


def _group_by_unit(leases: list) -> dict[str, list]:
    result: dict[str, list] = {}
    for le in leases:
        result.setdefault(le.unit_id, []).append(le)
    return result
