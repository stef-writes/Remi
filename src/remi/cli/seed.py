"""``remi seed`` — populate demo data for development and demos."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import typer

from remi.models.properties import (
    Address,
    Lease,
    LeaseStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
    OccupancyStatus,
    Portfolio,
    Priority,
    Property,
    PropertyManager,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)

cmd = typer.Typer(name="seed", help="Load demo data into the running REMI instance.")

TODAY = date.today()


def _date(days_offset: int) -> date:
    return TODAY + timedelta(days=days_offset)


# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------

MANAGERS = [
    PropertyManager(
        id="mgr-alice",
        name="Alice Chen Management",
        email="alice@chenpm.com",
        phone="503-555-0101",
        manager_tag="Alice Chen Management",
        portfolio_ids=["pf-alice"],
    ),
    PropertyManager(
        id="mgr-bob",
        name="Bob Diaz Properties",
        email="bob@diazprops.com",
        phone="503-555-0202",
        manager_tag="Bob Diaz Properties",
        portfolio_ids=["pf-bob"],
    ),
]

PORTFOLIOS = [
    Portfolio(id="pf-alice", manager_id="mgr-alice", name="Chen Portland Portfolio"),
    Portfolio(id="pf-bob", manager_id="mgr-bob", name="Diaz Metro Portfolio"),
]


def _addr(street, city="Portland", state="OR", z="97201"):
    return Address(
        street=street,
        city=city,
        state=state,
        zip_code=z,
    )


PROPERTIES = [
    Property(id="prop-oak", portfolio_id="pf-alice", name="Oak Tower", address=_addr("100 Oak St")),
    Property(
        id="prop-elm", portfolio_id="pf-alice", name="Elm Gardens", address=_addr("250 Elm Ave")
    ),
    Property(
        id="prop-pine", portfolio_id="pf-alice", name="Pine Ridge", address=_addr("88 Pine Blvd")
    ),
    Property(
        id="prop-cedar",
        portfolio_id="pf-bob",
        name="Cedar Heights",
        address=_addr("400 Cedar Ln", "Beaverton", "OR", "97005"),
    ),
    Property(
        id="prop-maple",
        portfolio_id="pf-bob",
        name="Maple Court",
        address=_addr("55 Maple Dr", "Lake Oswego", "OR", "97034"),
    ),
    Property(
        id="prop-birch", portfolio_id="pf-bob", name="Birch Flats", address=_addr("12 Birch Way")
    ),
]

# (unit_id, property_id, unit#, beds, baths, sqft, market_rent,
#  current_rent, status, occ_status, days_vacant)
_UNITS_RAW: list[tuple] = [
    # Oak Tower — 6 units, 1 vacant
    ("u-oak-101", "prop-oak", "101", 2, 1.0, 850, 1800, 1750, "occupied", "occupied", None),
    ("u-oak-102", "prop-oak", "102", 1, 1.0, 600, 1400, 1400, "occupied", "occupied", None),
    ("u-oak-103", "prop-oak", "103", 2, 1.0, 850, 1800, 1650, "occupied", "occupied", None),
    ("u-oak-104", "prop-oak", "104", 3, 2.0, 1100, 2200, 0, "vacant", "vacant_unrented", 45),
    ("u-oak-105", "prop-oak", "105", 1, 1.0, 600, 1400, 1400, "occupied", "occupied", None),
    ("u-oak-106", "prop-oak", "106", 2, 1.0, 850, 1800, 1800, "occupied", "notice_rented", None),
    # Elm Gardens — 4 units, 1 vacant
    ("u-elm-a", "prop-elm", "A", 2, 1.0, 900, 1900, 1850, "occupied", "occupied", None),
    ("u-elm-b", "prop-elm", "B", 2, 1.0, 900, 1900, 1900, "occupied", "occupied", None),
    ("u-elm-c", "prop-elm", "C", 1, 1.0, 650, 1500, 0, "vacant", "vacant_rented", 12),
    ("u-elm-d", "prop-elm", "D", 3, 2.0, 1200, 2400, 2200, "occupied", "occupied", None),
    # Pine Ridge — 5 units, all occupied
    ("u-pine-1", "prop-pine", "1", 1, 1.0, 550, 1300, 1250, "occupied", "occupied", None),
    ("u-pine-2", "prop-pine", "2", 2, 1.0, 800, 1700, 1700, "occupied", "occupied", None),
    ("u-pine-3", "prop-pine", "3", 2, 1.0, 800, 1700, 1550, "occupied", "occupied", None),
    ("u-pine-4", "prop-pine", "4", 3, 2.0, 1050, 2100, 2100, "occupied", "occupied", None),
    ("u-pine-5", "prop-pine", "5", 1, 1.0, 550, 1300, 1300, "occupied", "occupied", None),
    # Cedar Heights — 6 units, 2 vacant
    ("u-cedar-1", "prop-cedar", "1", 2, 1.0, 820, 1750, 1700, "occupied", "occupied", None),
    ("u-cedar-2", "prop-cedar", "2", 1, 1.0, 580, 1350, 0, "vacant", "vacant_unrented", 67),
    ("u-cedar-3", "prop-cedar", "3", 2, 1.0, 820, 1750, 1750, "occupied", "occupied", None),
    ("u-cedar-4", "prop-cedar", "4", 3, 2.0, 1100, 2300, 2100, "occupied", "occupied", None),
    ("u-cedar-5", "prop-cedar", "5", 1, 1.0, 580, 1350, 0, "vacant", "vacant_unrented", 30),
    ("u-cedar-6", "prop-cedar", "6", 2, 1.0, 820, 1750, 1750, "occupied", "notice_unrented", None),
    # Maple Court — 4 units, all occupied
    ("u-maple-1", "prop-maple", "1", 2, 2.0, 950, 2000, 1950, "occupied", "occupied", None),
    ("u-maple-2", "prop-maple", "2", 2, 2.0, 950, 2000, 2000, "occupied", "occupied", None),
    ("u-maple-3", "prop-maple", "3", 3, 2.0, 1200, 2500, 2500, "occupied", "occupied", None),
    ("u-maple-4", "prop-maple", "4", 1, 1.0, 600, 1400, 1350, "occupied", "occupied", None),
    # Birch Flats — 4 units, 1 vacant
    ("u-birch-1", "prop-birch", "1", 1, 1.0, 550, 1250, 1200, "occupied", "occupied", None),
    ("u-birch-2", "prop-birch", "2", 2, 1.0, 800, 1650, 1650, "occupied", "occupied", None),
    ("u-birch-3", "prop-birch", "3", 2, 1.0, 800, 1650, 0, "vacant", "vacant_unrented", 22),
    ("u-birch-4", "prop-birch", "4", 1, 1.0, 550, 1250, 1250, "occupied", "occupied", None),
]


def _build_units() -> list[Unit]:
    units = []
    for row in _UNITS_RAW:
        uid, pid, num, beds, baths, sqft, mr, cr, st, occ, dv = row
        units.append(
            Unit(
                id=uid,
                property_id=pid,
                unit_number=num,
                bedrooms=beds,
                bathrooms=baths,
                sqft=sqft,
                market_rent=Decimal(str(mr)),
                current_rent=Decimal(str(cr)),
                status=UnitStatus(st),
                occupancy_status=OccupancyStatus(occ) if occ else None,
                days_vacant=dv,
                listed_on_website=dv is not None and dv > 14,
            )
        )
    return units


# (tenant_id, name, status, balance_owed, balance_0_30, balance_30_plus, last_payment_offset_days)
_TENANTS_RAW: list[tuple] = [
    # Alice's tenants
    ("t-oak-101", "Maria Santos", "current", 0, 0, 0, -5),
    ("t-oak-102", "James Lee", "current", 0, 0, 0, -3),
    ("t-oak-103", "Priya Patel", "current", 1400, 1400, 0, -35),  # 1 month behind
    ("t-oak-105", "David Kim", "current", 0, 0, 0, -2),
    ("t-oak-106", "Sarah Wilson", "notice", 0, 0, 0, -8),
    ("t-elm-a", "Carlos Rivera", "current", 0, 0, 0, -4),
    ("t-elm-b", "Aisha Johnson", "current", 0, 0, 0, -1),
    ("t-elm-d", "Tom Nguyen", "current", 4200, 2200, 2000, -62),  # 2 months behind
    ("t-pine-1", "Lisa Chang", "current", 0, 0, 0, -6),
    ("t-pine-2", "Mark Thompson", "current", 0, 0, 0, -3),
    ("t-pine-3", "Rachel Adams", "current", 0, 0, 0, -7),
    ("t-pine-4", "Kevin Brown", "current", 0, 0, 0, -2),
    ("t-pine-5", "Amy Rodriguez", "current", 0, 0, 0, -5),
    # Bob's tenants
    ("t-cedar-1", "Diana Foster", "current", 0, 0, 0, -4),
    ("t-cedar-3", "Brian Clark", "current", 0, 0, 0, -2),
    ("t-cedar-4", "Yuki Tanaka", "current", 2300, 2300, 0, -40),  # 1 month behind
    ("t-cedar-6", "Nina Petrova", "notice", 3500, 1750, 1750, -55),  # 2 months, notice
    ("t-maple-1", "Frank Reyes", "current", 0, 0, 0, -3),
    ("t-maple-2", "Grace Liu", "current", 0, 0, 0, -6),
    ("t-maple-3", "Henry Walker", "current", 0, 0, 0, -1),
    ("t-maple-4", "Irene Park", "current", 0, 0, 0, -4),
    ("t-birch-1", "Jake Martin", "current", 0, 0, 0, -5),
    ("t-birch-2", "Karen White", "current", 1650, 1650, 0, -33),  # 1 month behind
    ("t-birch-4", "Leo Gomez", "current", 0, 0, 0, -2),
]


def _build_tenants() -> list[Tenant]:
    tenants = []
    for row in _TENANTS_RAW:
        tid, name, st, bal, b30, b30p, lpd = row
        tenants.append(
            Tenant(
                id=tid,
                name=name,
                status=TenantStatus(st),
                balance_owed=Decimal(str(bal)),
                balance_0_30=Decimal(str(b30)),
                balance_30_plus=Decimal(str(b30p)),
                last_payment_date=_date(lpd) if lpd else None,
                lease_ids=[f"lease-{tid}"],
            )
        )
    return tenants


# Map occupied unit → tenant for lease generation
_UNIT_TENANT = {
    "u-oak-101": "t-oak-101",
    "u-oak-102": "t-oak-102",
    "u-oak-103": "t-oak-103",
    "u-oak-105": "t-oak-105",
    "u-oak-106": "t-oak-106",
    "u-elm-a": "t-elm-a",
    "u-elm-b": "t-elm-b",
    "u-elm-d": "t-elm-d",
    "u-pine-1": "t-pine-1",
    "u-pine-2": "t-pine-2",
    "u-pine-3": "t-pine-3",
    "u-pine-4": "t-pine-4",
    "u-pine-5": "t-pine-5",
    "u-cedar-1": "t-cedar-1",
    "u-cedar-3": "t-cedar-3",
    "u-cedar-4": "t-cedar-4",
    "u-cedar-6": "t-cedar-6",
    "u-maple-1": "t-maple-1",
    "u-maple-2": "t-maple-2",
    "u-maple-3": "t-maple-3",
    "u-maple-4": "t-maple-4",
    "u-birch-1": "t-birch-1",
    "u-birch-2": "t-birch-2",
    "u-birch-4": "t-birch-4",
}

# Leases expiring soon (within 30-90 days) — makes the dashboard interesting
_SOON_EXPIRING = {
    "u-oak-103",
    "u-oak-106",
    "u-elm-d",
    "u-cedar-4",
    "u-cedar-6",
    "u-maple-4",
    "u-birch-2",
}
_MTM_UNITS = {"u-pine-1", "u-birch-1"}


def _build_leases(units: list[Unit]) -> list[Lease]:
    leases = []
    for u in units:
        tid = _UNIT_TENANT.get(u.id)
        if not tid:
            continue
        if u.id in _SOON_EXPIRING:
            start = _date(-335)
            end = _date(30 + hash(u.id) % 60)
        elif u.id in _MTM_UNITS:
            start = _date(-400)
            end = _date(-30)
        else:
            start = _date(-200)
            end = _date(165)

        leases.append(
            Lease(
                id=f"lease-{tid}",
                unit_id=u.id,
                tenant_id=tid,
                property_id=u.property_id,
                start_date=start,
                end_date=end,
                monthly_rent=u.current_rent,
                market_rent=u.market_rent,
                status=LeaseStatus.ACTIVE,
                is_month_to_month=u.id in _MTM_UNITS,
            )
        )
    return leases


MAINTENANCE: list[MaintenanceRequest] = [
    MaintenanceRequest(
        id="mx-1",
        unit_id="u-oak-104",
        property_id="prop-oak",
        category=MaintenanceCategory.PLUMBING,
        priority=Priority.HIGH,
        title="Leaking kitchen faucet",
        description="Constant drip, water damage forming under sink.",
        status=MaintenanceStatus.OPEN,
    ),
    MaintenanceRequest(
        id="mx-2",
        unit_id="u-oak-103",
        property_id="prop-oak",
        tenant_id="t-oak-103",
        category=MaintenanceCategory.HVAC,
        priority=Priority.MEDIUM,
        title="AC not cooling",
        description="Unit reports AC blows warm air. Filter replaced last month.",
        status=MaintenanceStatus.IN_PROGRESS,
        vendor="CoolAir HVAC",
    ),
    MaintenanceRequest(
        id="mx-3",
        unit_id="u-cedar-2",
        property_id="prop-cedar",
        category=MaintenanceCategory.APPLIANCE,
        priority=Priority.MEDIUM,
        title="Dishwasher not draining",
        description="Standing water after cycle completes.",
        status=MaintenanceStatus.OPEN,
    ),
    MaintenanceRequest(
        id="mx-4",
        unit_id="u-cedar-5",
        property_id="prop-cedar",
        category=MaintenanceCategory.ELECTRICAL,
        priority=Priority.HIGH,
        title="Bathroom outlet sparking",
        description="Outlet near sink sparks when anything plugged in.",
        status=MaintenanceStatus.OPEN,
    ),
    MaintenanceRequest(
        id="mx-5",
        unit_id="u-birch-3",
        property_id="prop-birch",
        category=MaintenanceCategory.GENERAL,
        priority=Priority.LOW,
        title="Touch-up paint needed",
        description="Scuffs on hallway walls from previous tenant.",
        status=MaintenanceStatus.OPEN,
    ),
    MaintenanceRequest(
        id="mx-6",
        unit_id="u-elm-d",
        property_id="prop-elm",
        tenant_id="t-elm-d",
        category=MaintenanceCategory.STRUCTURAL,
        priority=Priority.HIGH,
        title="Ceiling crack in bedroom",
        description="Hairline crack growing wider over past 2 months.",
        status=MaintenanceStatus.OPEN,
    ),
    MaintenanceRequest(
        id="mx-7",
        unit_id="u-maple-3",
        property_id="prop-maple",
        tenant_id="t-maple-3",
        category=MaintenanceCategory.PLUMBING,
        priority=Priority.EMERGENCY,
        title="Toilet overflow",
        description="Main bathroom toilet overflowing, water on floor.",
        status=MaintenanceStatus.IN_PROGRESS,
        vendor="PDX Plumbing",
    ),
]


async def seed_into(ps: Any) -> str:
    """Insert demo data into the given property store. Returns summary string."""
    for m in MANAGERS:
        await ps.upsert_manager(m)
    for p in PORTFOLIOS:
        await ps.upsert_portfolio(p)
    for prop in PROPERTIES:
        await ps.upsert_property(prop)

    units = _build_units()
    for u in units:
        await ps.upsert_unit(u)

    tenants = _build_tenants()
    for t in tenants:
        await ps.upsert_tenant(t)

    leases = _build_leases(units)
    for le in leases:
        await ps.upsert_lease(le)

    for mx in MAINTENANCE:
        await ps.upsert_maintenance_request(mx)

    return (
        f"Seeded: {len(MANAGERS)} managers, {len(PORTFOLIOS)} portfolios, "
        f"{len(PROPERTIES)} properties, {len(units)} units, "
        f"{len(tenants)} tenants, {len(leases)} leases, "
        f"{len(MAINTENANCE)} maintenance requests."
    )


async def _seed() -> None:
    from remi.cli.shared import get_container_async

    container = await get_container_async()
    summary = await seed_into(container.property_store)
    typer.echo(summary)


@cmd.callback(invoke_without_command=True)
def seed() -> None:
    """Load demo data (managers, properties, units, leases, tenants, maintenance)."""
    asyncio.run(_seed())
