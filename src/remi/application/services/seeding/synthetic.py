"""Synthetic portfolio generator — realistic demo data with no LLM calls.

Creates managers, portfolios, properties, units, tenants, and leases
directly in the PropertyStore.  Designed for ``remi seed --generate``
so demos work from a fresh clone without XLSX files or API keys.

Data is seeded with a fixed RNG for reproducibility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import structlog

from remi.application.core.models import (
    Address,
    Lease,
    LeaseStatus,
    OccupancyStatus,
    Portfolio,
    Property,
    PropertyManager,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)
from remi.application.core.protocols import PropertyStore

logger = structlog.get_logger(__name__)

_MANAGER_NAMES = [
    "Alex Budavich",
    "Maria Santos",
    "James Chen",
]

_STREETS = [
    ("1018 Woodbourne Ave", "Pittsburgh", "PA", "15226"),
    ("742 Maple Drive", "Pittsburgh", "PA", "15213"),
    ("330 Centre Ave", "Pittsburgh", "PA", "15232"),
    ("1205 Penn Ave", "Pittsburgh", "PA", "15222"),
    ("850 Ridge Ave", "Pittsburgh", "PA", "15212"),
    ("422 Murray Ave", "Pittsburgh", "PA", "15217"),
    ("1100 Walnut St", "Pittsburgh", "PA", "15232"),
    ("205 Shady Ave", "Pittsburgh", "PA", "15206"),
    ("615 Ellsworth Ave", "Pittsburgh", "PA", "15232"),
    ("901 Western Ave", "Pittsburgh", "PA", "15233"),
    ("1430 Beechwood Blvd", "Pittsburgh", "PA", "15217"),
    ("540 Forbes Ave", "Pittsburgh", "PA", "15219"),
]

_FIRST_NAMES = [
    "James", "Maria", "David", "Sarah", "Michael", "Linda", "Robert",
    "Patricia", "John", "Jennifer", "William", "Elizabeth", "Carlos",
    "Angela", "Thomas", "Barbara", "Kevin", "Susan", "Daniel", "Nancy",
    "Mark", "Karen", "Steven", "Lisa", "Paul", "Donna", "Andrew",
    "Michelle", "Brian", "Sandra",
]

_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson",
    "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee",
]


@dataclass
class SyntheticResult:
    managers: int = 0
    portfolios: int = 0
    properties: int = 0
    units: int = 0
    tenants: int = 0
    leases: int = 0
    errors: list[str] = field(default_factory=list)


async def generate_synthetic_portfolio(
    store: PropertyStore,
    *,
    seed: int = 42,
) -> SyntheticResult:
    """Populate the store with realistic synthetic data."""
    rng = random.Random(seed)
    result = SyntheticResult()
    today = date.today()

    prop_idx = 0

    for mgr_idx, mgr_name in enumerate(_MANAGER_NAMES):
        mgr_id = f"mgr-{mgr_idx + 1}"
        port_id = f"port-{mgr_idx + 1}"

        await store.upsert_manager(PropertyManager(
            id=mgr_id,
            name=mgr_name,
            email=f"{mgr_name.lower().replace(' ', '.')}@example.com",
            company="Demo Property Management",
            portfolio_ids=[port_id],
        ))
        result.managers += 1

        num_properties = rng.randint(2, 5)
        property_ids: list[str] = []

        for _ in range(num_properties):
            if prop_idx >= len(_STREETS):
                break
            street, city, state, zipcode = _STREETS[prop_idx]
            prop_id = f"prop-{prop_idx + 1}"
            property_ids.append(prop_id)

            await store.upsert_property(Property(
                id=prop_id,
                portfolio_id=port_id,
                name=street,
                address=Address(
                    street=street, city=city, state=state, zip_code=zipcode,
                ),
            ))
            result.properties += 1

            num_units = rng.randint(4, 12)
            for u in range(num_units):
                unit_id = f"unit-{prop_id}-{u + 1}"
                bedrooms = rng.choice([1, 1, 2, 2, 2, 3, 3])
                market_rent = Decimal(str(rng.randint(800, 1800)))
                is_occupied = rng.random() < 0.88

                if is_occupied:
                    current_rent = market_rent - Decimal(str(rng.randint(0, 100)))
                    status = UnitStatus.OCCUPIED
                    occ_status = OccupancyStatus.OCCUPIED
                    days_vacant = None
                else:
                    current_rent = Decimal("0")
                    status = UnitStatus.VACANT
                    occ_status = rng.choice([
                        OccupancyStatus.VACANT_UNRENTED,
                        OccupancyStatus.VACANT_RENTED,
                    ])
                    days_vacant = rng.randint(5, 90)

                await store.upsert_unit(Unit(
                    id=unit_id,
                    property_id=prop_id,
                    unit_number=str(u + 1),
                    bedrooms=bedrooms,
                    bathrooms=1.0 if bedrooms <= 2 else 1.5,
                    sqft=rng.randint(500, 1200),
                    market_rent=market_rent,
                    current_rent=current_rent,
                    status=status,
                    occupancy_status=occ_status,
                    days_vacant=days_vacant,
                ))
                result.units += 1

                if is_occupied:
                    first = rng.choice(_FIRST_NAMES)
                    last = rng.choice(_LAST_NAMES)
                    tenant_id = f"tenant-{unit_id}"

                    is_delinquent = rng.random() < 0.15
                    balance = (
                        Decimal(str(rng.randint(200, 3000)))
                        if is_delinquent else Decimal("0")
                    )
                    tenant_status = (
                        TenantStatus.DELINQUENT if is_delinquent
                        else TenantStatus.CURRENT
                    )

                    lease_start = today - timedelta(days=rng.randint(60, 400))
                    lease_end = lease_start + timedelta(days=365)
                    lease_status = (
                        LeaseStatus.ACTIVE if lease_end > today
                        else LeaseStatus.EXPIRED
                    )

                    lease_id = f"lease-{unit_id}"

                    await store.upsert_tenant(Tenant(
                        id=tenant_id,
                        name=f"{first} {last}",
                        email=f"{first.lower()}.{last.lower()}@email.com",
                        status=tenant_status,
                        balance_owed=balance,
                        balance_0_30=balance if is_delinquent else Decimal("0"),
                        lease_ids=[lease_id],
                    ))
                    result.tenants += 1

                    await store.upsert_lease(Lease(
                        id=lease_id,
                        unit_id=unit_id,
                        tenant_id=tenant_id,
                        property_id=prop_id,
                        start_date=lease_start,
                        end_date=lease_end,
                        monthly_rent=current_rent,
                        market_rent=market_rent,
                        status=lease_status,
                    ))
                    result.leases += 1

            prop_idx += 1

        await store.upsert_portfolio(Portfolio(
            id=port_id,
            manager_id=mgr_id,
            name=f"{mgr_name} Portfolio",
            property_ids=property_ids,
        ))
        result.portfolios += 1

    logger.info(
        "synthetic_portfolio_generated",
        managers=result.managers,
        properties=result.properties,
        units=result.units,
        tenants=result.tenants,
        leases=result.leases,
    )
    return result
