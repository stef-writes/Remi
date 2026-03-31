"""StatisticalProducer — data-driven signal detection over OntologyStore.

Domain-agnostic: works on any object type with numeric fields. Detects:

1. **Outliers** — values significantly outside the norm for their type
   (z-score > threshold, using mean/stddev per numeric field)

2. **Distribution skew** — when a categorical field's distribution is
   highly concentrated (single value > threshold % of total)

No hand-authored rules. No domain knowledge required. Operates purely
through the OntologyStore port. Produces signals with
``provenance=DATA_DERIVED``.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from remi.models.ontology import OntologyStore
from remi.models.signals import ProducerResult, Provenance, Severity, Signal, SignalProducer

_log = structlog.get_logger(__name__)


def _signal_id(detection_type: str, type_name: str, field: str, entity_id: str) -> str:
    return f"signal:stat:{detection_type}:{type_name}.{field}:{entity_id}"


class StatisticalProducer(SignalProducer):
    """Detects statistical anomalies across OntologyStore data.

    Scans every registered object type, computes descriptive stats on
    numeric fields, and flags outliers. No rules, no thresholds from YAML —
    purely data-driven.
    """

    def __init__(
        self,
        ontology_store: OntologyStore,
        *,
        zscore_threshold: float = 2.5,
        concentration_threshold: float = 0.80,
        min_sample_size: int = 5,
    ) -> None:
        self._os = ontology_store
        self._zscore_threshold = zscore_threshold
        self._concentration_threshold = concentration_threshold
        self._min_sample_size = min_sample_size

    @property
    def name(self) -> str:
        return "statistical"

    async def evaluate(self) -> ProducerResult:
        result = ProducerResult(source=self.name)
        types = await self._os.list_object_types()

        for type_def in types:
            try:
                objects = await self._os.search_objects(
                    type_def.name,
                    limit=10_000,
                )
                if len(objects) < self._min_sample_size:
                    continue

                numeric_fields = self._identify_numeric_fields(objects)
                for field_name in numeric_fields:
                    outliers = self._detect_outliers(
                        objects,
                        type_def.name,
                        field_name,
                    )
                    for sig in outliers:
                        result.signals.append(sig)
                        result.produced += 1

                categorical_fields = self._identify_categorical_fields(
                    objects,
                    exclude=numeric_fields,
                )
                for field_name in categorical_fields:
                    concentration = self._detect_concentration(
                        objects,
                        type_def.name,
                        field_name,
                    )
                    for sig in concentration:
                        result.signals.append(sig)
                        result.produced += 1

            except Exception:
                result.errors += 1
                _log.warning(
                    "statistical_type_scan_failed",
                    type_name=type_def.name,
                    exc_info=True,
                )

        _log.info(
            "statistical_evaluation_complete",
            produced=result.produced,
            errors=result.errors,
            types_scanned=len(types),
        )
        return result

    def _identify_numeric_fields(self, objects: list[dict[str, Any]]) -> list[str]:
        """Find fields that are consistently numeric across the sample."""
        if not objects:
            return []

        candidates: dict[str, int] = {}
        sample = objects[:100]
        for obj in sample:
            for key, val in obj.items():
                if key == "id":
                    continue
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    candidates[key] = candidates.get(key, 0) + 1

        threshold = len(sample) * 0.5
        return [k for k, count in candidates.items() if count >= threshold]

    def _identify_categorical_fields(
        self,
        objects: list[dict[str, Any]],
        *,
        exclude: list[str],
    ) -> list[str]:
        """Find string fields suitable for distribution analysis."""
        if not objects:
            return []

        exclude_set = set(exclude) | {"id", "name", "description", "email"}
        candidates: dict[str, int] = {}
        sample = objects[:100]

        for obj in sample:
            for key, val in obj.items():
                if key in exclude_set:
                    continue
                if isinstance(val, str) and len(val) < 100:
                    candidates[key] = candidates.get(key, 0) + 1

        threshold = len(sample) * 0.5
        return [k for k, count in candidates.items() if count >= threshold]

    def _detect_outliers(
        self,
        objects: list[dict[str, Any]],
        type_name: str,
        field_name: str,
    ) -> list[Signal]:
        """Z-score outlier detection on a numeric field."""
        values: list[tuple[str, float]] = []
        for obj in objects:
            val = obj.get(field_name)
            if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
                entity_id = str(obj.get("id", ""))
                values.append((entity_id, float(val)))

        if len(values) < self._min_sample_size:
            return []

        nums = [v for _, v in values]
        mean = sum(nums) / len(nums)
        variance = sum((x - mean) ** 2 for x in nums) / len(nums)
        stddev = math.sqrt(variance) if variance > 0 else 0

        if stddev == 0:
            return []

        signals: list[Signal] = []
        for entity_id, val in values:
            zscore = (val - mean) / stddev
            if abs(zscore) >= self._zscore_threshold:
                direction = "above" if zscore > 0 else "below"
                severity = (
                    Severity.HIGH
                    if abs(zscore) >= 3.5
                    else Severity.MEDIUM
                    if abs(zscore) >= 3.0
                    else Severity.LOW
                )
                signals.append(
                    Signal(
                        signal_id=_signal_id("outlier", type_name, field_name, entity_id),
                        signal_type=f"StatisticalOutlier:{type_name}.{field_name}",
                        severity=severity,
                        entity_type=type_name,
                        entity_id=entity_id,
                        entity_name=entity_id,
                        description=(
                            f"{field_name}={val:.2f} is {abs(zscore):.1f} std devs "
                            f"{direction} mean ({mean:.2f}) for {type_name}"
                        ),
                        evidence={
                            "field": field_name,
                            "value": val,
                            "mean": round(mean, 4),
                            "stddev": round(stddev, 4),
                            "zscore": round(zscore, 4),
                            "sample_size": len(values),
                            "detection": "zscore_outlier",
                        },
                        provenance=Provenance.DATA_DERIVED,
                    )
                )
        return signals

    def _detect_concentration(
        self,
        objects: list[dict[str, Any]],
        type_name: str,
        field_name: str,
    ) -> list[Signal]:
        """Detect when a categorical field is highly concentrated."""
        counts: dict[str, int] = {}
        total = 0

        for obj in objects:
            val = obj.get(field_name)
            if val is not None and isinstance(val, str):
                counts[val] = counts.get(val, 0) + 1
                total += 1

        if total < self._min_sample_size:
            return []

        signals: list[Signal] = []
        for value, count in counts.items():
            pct = count / total
            if pct >= self._concentration_threshold:
                signals.append(
                    Signal(
                        signal_id=_signal_id(
                            "concentration",
                            type_name,
                            field_name,
                            value.replace(" ", "_")[:20],
                        ),
                        signal_type=f"ConcentrationRisk:{type_name}.{field_name}",
                        severity=Severity.LOW,
                        entity_type=type_name,
                        entity_id=f"{type_name}:{field_name}:{value}",
                        entity_name=f"{type_name}.{field_name}",
                        description=(
                            f"{pct:.0%} of {type_name} objects have "
                            f"{field_name}='{value}' ({count}/{total})"
                        ),
                        evidence={
                            "field": field_name,
                            "dominant_value": value,
                            "count": count,
                            "total": total,
                            "percentage": round(pct, 4),
                            "detection": "categorical_concentration",
                        },
                        provenance=Provenance.DATA_DERIVED,
                    )
                )
        return signals
