"""Merged models module."""

from __future__ import annotations

import abc
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class PropertyType(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MIXED = "mixed"
    INDUSTRIAL = "industrial"


class UnitStatus(StrEnum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class LeaseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    PENDING = "pending"


class MaintenanceCategory(StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    APPLIANCE = "appliance"
    STRUCTURAL = "structural"
    GENERAL = "general"
    OTHER = "other"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EMERGENCY = "emergency"


class MaintenanceStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OccupancyStatus(StrEnum):
    OCCUPIED = "occupied"
    NOTICE_RENTED = "notice_rented"
    NOTICE_UNRENTED = "notice_unrented"
    VACANT_RENTED = "vacant_rented"
    VACANT_UNRENTED = "vacant_unrented"


class TenantStatus(StrEnum):
    CURRENT = "current"
    NOTICE = "notice"
    EVICT = "evict"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Address(BaseModel, frozen=True):
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"

    def one_line(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


class PropertyManager(BaseModel, frozen=True):
    id: str
    name: str
    email: str = ""
    company: str | None = None
    phone: str | None = None
    manager_tag: str | None = None
    portfolio_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Portfolio(BaseModel, frozen=True):
    id: str
    manager_id: str
    name: str
    description: str = ""
    property_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class Property(BaseModel, frozen=True):
    id: str
    portfolio_id: str
    name: str
    address: Address
    property_type: PropertyType = PropertyType.RESIDENTIAL
    year_built: int | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class Unit(BaseModel, frozen=True):
    id: str
    property_id: str
    unit_number: str
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft: int | None = None
    market_rent: Decimal = Decimal("0")
    current_rent: Decimal = Decimal("0")
    status: UnitStatus = UnitStatus.VACANT
    occupancy_status: OccupancyStatus | None = None
    days_vacant: int | None = None
    listed_on_website: bool = False
    listed_on_internet: bool = False
    floor: int | None = None


class Lease(BaseModel, frozen=True):
    id: str
    unit_id: str
    tenant_id: str
    property_id: str
    start_date: date
    end_date: date
    monthly_rent: Decimal
    deposit: Decimal = Decimal("0")
    status: LeaseStatus = LeaseStatus.ACTIVE
    market_rent: Decimal = Decimal("0")
    is_month_to_month: bool = False


class Tenant(BaseModel, frozen=True):
    id: str
    name: str
    email: str = ""
    phone: str | None = None
    status: TenantStatus = TenantStatus.CURRENT
    balance_owed: Decimal = Decimal("0")
    balance_0_30: Decimal = Decimal("0")
    balance_30_plus: Decimal = Decimal("0")
    last_payment_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    lease_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class MaintenanceRequest(BaseModel, frozen=True):
    id: str
    unit_id: str
    property_id: str
    tenant_id: str | None = None
    category: MaintenanceCategory = MaintenanceCategory.GENERAL
    priority: Priority = Priority.MEDIUM
    title: str = ""
    description: str = ""
    status: MaintenanceStatus = MaintenanceStatus.OPEN
    created_at: datetime = Field(default_factory=_utcnow)
    resolved_at: datetime | None = None
    cost: Decimal | None = None
    vendor: str | None = None


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


class PropertyStore(abc.ABC):
    """Read/write access to the core property management entities."""

    # -- Property Managers --
    @abc.abstractmethod
    async def get_manager(self, manager_id: str) -> PropertyManager | None: ...

    @abc.abstractmethod
    async def list_managers(self) -> list[PropertyManager]: ...

    @abc.abstractmethod
    async def upsert_manager(self, manager: PropertyManager) -> None: ...

    # -- Portfolios --
    @abc.abstractmethod
    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None: ...

    @abc.abstractmethod
    async def list_portfolios(self, *, manager_id: str | None = None) -> list[Portfolio]: ...

    @abc.abstractmethod
    async def upsert_portfolio(self, portfolio: Portfolio) -> None: ...

    # -- Properties --
    @abc.abstractmethod
    async def get_property(self, property_id: str) -> Property | None: ...

    @abc.abstractmethod
    async def list_properties(self, *, portfolio_id: str | None = None) -> list[Property]: ...

    @abc.abstractmethod
    async def upsert_property(self, prop: Property) -> None: ...

    # -- Units --
    @abc.abstractmethod
    async def get_unit(self, unit_id: str) -> Unit | None: ...

    @abc.abstractmethod
    async def list_units(
        self,
        *,
        property_id: str | None = None,
        status: UnitStatus | None = None,
        occupancy_status: OccupancyStatus | None = None,
    ) -> list[Unit]: ...

    @abc.abstractmethod
    async def upsert_unit(self, unit: Unit) -> None: ...

    # -- Leases --
    @abc.abstractmethod
    async def get_lease(self, lease_id: str) -> Lease | None: ...

    @abc.abstractmethod
    async def list_leases(
        self,
        *,
        unit_id: str | None = None,
        tenant_id: str | None = None,
        property_id: str | None = None,
        status: LeaseStatus | None = None,
    ) -> list[Lease]: ...

    @abc.abstractmethod
    async def upsert_lease(self, lease: Lease) -> None: ...

    # -- Tenants --
    @abc.abstractmethod
    async def get_tenant(self, tenant_id: str) -> Tenant | None: ...

    @abc.abstractmethod
    async def list_tenants(
        self,
        *,
        property_id: str | None = None,
        status: TenantStatus | None = None,
    ) -> list[Tenant]: ...

    @abc.abstractmethod
    async def upsert_tenant(self, tenant: Tenant) -> None: ...

    # -- Maintenance --
    @abc.abstractmethod
    async def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None: ...

    @abc.abstractmethod
    async def list_maintenance_requests(
        self,
        *,
        property_id: str | None = None,
        unit_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]: ...

    @abc.abstractmethod
    async def upsert_maintenance_request(self, request: MaintenanceRequest) -> None: ...
