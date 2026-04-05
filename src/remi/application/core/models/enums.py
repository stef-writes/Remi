"""Shared vocabulary — statuses, categories, types.

Pure enums with no dependencies.  Every entity module imports from here.
"""

from __future__ import annotations

from enum import StrEnum


class EntityType(StrEnum):
    """Well-known entity types for the REMI real-estate product."""

    OWNER = "Owner"
    PROPERTY_MANAGER = "PropertyManager"
    PORTFOLIO = "Portfolio"
    PROPERTY = "Property"
    UNIT = "Unit"
    TENANT = "Tenant"
    LEASE = "Lease"
    VENDOR = "Vendor"
    MAINTENANCE_REQUEST = "MaintenanceRequest"


class PropertyType(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MIXED = "mixed"
    INDUSTRIAL = "industrial"


class AssetClass(StrEnum):
    A = "a"
    B = "b"
    C = "c"
    D = "d"


class UnitStatus(StrEnum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class UnitType(StrEnum):
    STUDIO = "studio"
    ONE_BED = "one_bed"
    TWO_BED = "two_bed"
    THREE_BED = "three_bed"
    FOUR_PLUS = "four_plus"
    COMMERCIAL = "commercial"
    STORAGE = "storage"
    OTHER = "other"


class OccupancyStatus(StrEnum):
    OCCUPIED = "occupied"
    NOTICE_RENTED = "notice_rented"
    NOTICE_UNRENTED = "notice_unrented"
    VACANT_RENTED = "vacant_rented"
    VACANT_UNRENTED = "vacant_unrented"


class LeaseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    PENDING = "pending"


class LeaseType(StrEnum):
    FIXED = "fixed"
    MONTH_TO_MONTH = "month_to_month"
    CORPORATE = "corporate"
    SECTION8 = "section8"
    STUDENT = "student"
    MILITARY = "military"
    OTHER = "other"


class RenewalStatus(StrEnum):
    NOT_STARTED = "not_started"
    OFFERED = "offered"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    LAPSED = "lapsed"


class TenantStatus(StrEnum):
    CURRENT = "current"
    NOTICE = "notice"
    DEMAND = "demand"
    FILING = "filing"
    HEARING = "hearing"
    JUDGMENT = "judgment"
    EVICT = "evict"
    PAST = "past"


class VendorCategory(StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    APPLIANCE = "appliance"
    GENERAL = "general"
    CLEANING = "cleaning"
    PAINTING = "painting"
    FLOORING = "flooring"
    ROOFING = "roofing"
    LANDSCAPING = "landscaping"
    OTHER = "other"


class MaintenanceCategory(StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    APPLIANCE = "appliance"
    STRUCTURAL = "structural"
    GENERAL = "general"
    OTHER = "other"


class MaintenanceSource(StrEnum):
    TENANT = "tenant"
    INSPECTION = "inspection"
    PREVENTIVE = "preventive"
    EMERGENCY = "emergency"
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


class ActionItemStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class ActionItemPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NoteProvenance(StrEnum):
    USER_STATED = "user_stated"
    DATA_DERIVED = "data_derived"
    INFERRED = "inferred"


class DocumentType(StrEnum):
    LEASE = "lease"
    AMENDMENT = "amendment"
    NOTICE = "notice"
    REPORT = "report"
    INSPECTION = "inspection"
    CORRESPONDENCE = "correspondence"
    OTHER = "other"
