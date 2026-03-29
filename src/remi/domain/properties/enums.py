"""Enumerations for the real estate domain."""

from __future__ import annotations

from enum import Enum


class PropertyType(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MIXED = "mixed"
    INDUSTRIAL = "industrial"


class UnitStatus(str, Enum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class LeaseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    PENDING = "pending"


class MaintenanceCategory(str, Enum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    APPLIANCE = "appliance"
    STRUCTURAL = "structural"
    GENERAL = "general"
    OTHER = "other"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EMERGENCY = "emergency"


class MaintenanceStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OccupancyStatus(str, Enum):
    OCCUPIED = "occupied"
    NOTICE_RENTED = "notice_rented"
    NOTICE_UNRENTED = "notice_unrented"
    VACANT_RENTED = "vacant_rented"
    VACANT_UNRENTED = "vacant_unrented"


class TenantStatus(str, Enum):
    CURRENT = "current"
    NOTICE = "notice"
    EVICT = "evict"
