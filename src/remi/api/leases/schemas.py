"""Response schemas for leases."""

from __future__ import annotations

from pydantic import BaseModel


class ExpiringLeaseItem(BaseModel):
    lease_id: str
    tenant: str
    unit: str
    property: str
    monthly_rent: float
    end_date: str
    days_left: int


class ExpiringLeasesResponse(BaseModel):
    days_window: int
    count: int
    leases: list[ExpiringLeaseItem]


class LeaseListItem(BaseModel):
    id: str
    tenant: str
    unit_id: str
    property_id: str
    start: str
    end: str
    rent: float
    status: str


class LeaseListResponse(BaseModel):
    count: int
    leases: list[LeaseListItem]
