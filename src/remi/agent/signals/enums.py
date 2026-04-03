"""Domain enums for the signal system."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"



class Horizon(StrEnum):
    CURRENT = "current"
    CURRENT_PERIOD = "current_period"
    TRAILING_60_DAYS = "trailing_60_days"
    TRAILING_90_DAYS = "trailing_90_days"
    NEXT_60_DAYS = "next_60_days"
    NEXT_90_DAYS = "next_90_days"
    EVENT_DRIVEN = "event_driven"


class RuleCondition(StrEnum):
    """The finite set of evaluation strategies the engine understands."""

    EXCEEDS_THRESHOLD = "exceeds_threshold"
    AGING_PAST_THRESHOLD = "aging_past_threshold"
    DECLINING_CONSECUTIVE_PERIODS = "declining_consecutive_periods"
    BELOW_PERCENTILE = "below_percentile"
    CONSISTENT_DIRECTION = "consistent_direction"
    IN_LEGAL_TRACK = "in_legal_track"
    STALLED_PAST_WINDOW = "stalled_past_window"
    EXISTS = "exists"
    BREACH_DETECTED = "breach_detected"


class Deontic(StrEnum):
    MUST = "MUST"
    SHOULD = "SHOULD"


class SignalOutcome(StrEnum):
    """What happened after a signal was surfaced."""

    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    ACTED_ON = "acted_on"
    ESCALATED = "escalated"
    FALSE_POSITIVE = "false_positive"
