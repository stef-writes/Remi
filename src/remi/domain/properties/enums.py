"""Enumerations for the real estate domain."""

from __future__ import annotations

from enum import StrEnum


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
