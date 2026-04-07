"""Shared vocabulary — statuses, categories, types.

Pure enums with no dependencies.  Every entity module imports from here.
"""

from __future__ import annotations

from enum import StrEnum


class EntityType(StrEnum):
    """Well-known entity types for the REMI real-estate product."""

    OWNER = "Owner"
    PROPERTY_MANAGER = "PropertyManager"
    PROPERTY = "Property"
    UNIT = "Unit"
    TENANT = "Tenant"
    LEASE = "Lease"
    VENDOR = "Vendor"
    MAINTENANCE_REQUEST = "MaintenanceRequest"


class OwnerType(StrEnum):
    """Legal structure of the property owner."""

    INDIVIDUAL = "individual"
    LLC = "llc"
    TRUST = "trust"
    PARTNERSHIP = "partnership"
    CORPORATION = "corporation"
    OTHER = "other"


class PropertyType(StrEnum):
    SINGLE_FAMILY = "single_family"
    MULTI_FAMILY = "multi_family"
    COMMERCIAL = "commercial"
    MIXED = "mixed"
    INDUSTRIAL = "industrial"


class AssetClass(StrEnum):
    A = "a"
    B = "b"
    C = "c"
    D = "d"


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


class TradeCategory(StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    HVAC = "hvac"
    APPLIANCE = "appliance"
    STRUCTURAL = "structural"
    GENERAL = "general"
    CLEANING = "cleaning"
    PAINTING = "painting"
    FLOORING = "flooring"
    ROOFING = "roofing"
    LANDSCAPING = "landscaping"
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
    URGENT = "urgent"
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


class ReportScope(StrEnum):
    """What slice of the portfolio a report covers.

    Populated by the extract pipeline from report metadata (header rows).
    Used to answer "do we have data for property X in period Y?" without
    scanning all rows.
    """

    UNKNOWN = "unknown"
    PORTFOLIO_WIDE = "portfolio_wide"  # all properties, all managers
    MANAGER_PORTFOLIO = "manager_portfolio"  # one manager's full book
    SINGLE_PROPERTY = "single_property"  # scoped to one property address
    SINGLE_UNIT = "single_unit"  # scoped to one unit


class ReportType(StrEnum):
    """The business category of a report — what domain data it contains.

    Values align with ``_ENTITY_TO_REPORT_TYPE`` in the matcher so that
    rule-matched and LLM-extracted reports share the same vocabulary.
    """

    UNKNOWN = "unknown"
    RENT_ROLL = "rent_roll"
    DELINQUENCY = "delinquency"
    WORK_ORDER = "work_order"
    LEASE_EXPIRATION = "lease_expiration"
    PROPERTY_DIRECTORY = "property_directory"
    TENANT_DIRECTORY = "tenant_directory"
    VENDOR_DIRECTORY = "vendor_directory"
    OWNER_DIRECTORY = "owner_directory"
    MANAGER_DIRECTORY = "manager_directory"
    OWNER_STATEMENT = "owner_statement"
    INSPECTION = "inspection"


class Platform(StrEnum):
    """Property management software the report was exported from."""

    UNKNOWN = "unknown"
    APPFOLIO = "appfolio"
    YARDI = "yardi"
    BUILDIUM = "buildium"
    REALPAGE = "realpage"
    ENTRATA = "entrata"
    PROPERTYWARE = "propertyware"


class ImportStatus(StrEnum):
    """Lifecycle state of a report import.

    COMPLETE means all rows were extracted and persisted.
    PARTIAL means some rows failed (see the source document's error log).
    FAILED means the import did not produce any entities.
    SUPERSEDED means a newer import for the same scope+period replaced this one.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    SUPERSEDED = "superseded"
