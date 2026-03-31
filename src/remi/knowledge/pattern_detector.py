"""PatternDetector — discovers candidate TBox entries from data patterns.

This is the induction layer. It examines ABox facts through the OntologyStore
and proposes new domain knowledge as Hypothesis objects:

- Outlier patterns → proposed SignalDefinitions ("this metric regularly
  exceeds N for certain entities — should we formalize a threshold?")
- Correlations → proposed CausalChains ("when X increases, Y decreases
  across this entity type — is this a causal relationship?")
- Concentration patterns → proposed schema observations ("80% of entities
  have the same value for field Z — is this meaningful?")

The detector does NOT produce Signals. It produces Hypotheses — candidate
laws that must be confirmed before they affect the system's deductive
reasoning.

Domain-agnostic: operates through OntologyStore, works on any object types.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from remi.models.ontology import OntologyStore
from remi.models.signals import (
    Hypothesis,
    HypothesisKind,
    HypothesisStore,
)

_log = structlog.get_logger(__name__)


def _hypothesis_id(kind: str, scope: str) -> str:
    return f"hyp:{kind}:{scope}:{uuid.uuid4().hex[:8]}"


@dataclass
class DetectorResult:
    """Output of a pattern detection run."""

    hypotheses: list[Hypothesis] = field(default_factory=list)
    proposed: int = 0
    errors: int = 0
    types_scanned: int = 0


class PatternDetector:
    """Discovers candidate domain knowledge from data patterns.

    Scans OntologyStore data, computes statistics, and proposes Hypothesis
    objects that represent potential new TBox entries. These must be
    reviewed and confirmed before becoming part of the domain's known physics.
    """

    def __init__(
        self,
        ontology_store: OntologyStore,
        hypothesis_store: HypothesisStore,
        *,
        zscore_threshold: float = 2.5,
        concentration_threshold: float = 0.80,
        correlation_threshold: float = 0.70,
        min_sample_size: int = 5,
    ) -> None:
        self._os = ontology_store
        self._hs = hypothesis_store
        self._zscore_threshold = zscore_threshold
        self._concentration_threshold = concentration_threshold
        self._correlation_threshold = correlation_threshold
        self._min_sample_size = min_sample_size

    async def run(self) -> DetectorResult:
        """Scan all object types and propose hypotheses from patterns."""
        result = DetectorResult()
        types = await self._os.list_object_types()
        result.types_scanned = len(types)

        for type_def in types:
            try:
                objects = await self._os.search_objects(
                    type_def.name,
                    limit=10_000,
                )
                if len(objects) < self._min_sample_size:
                    continue

                numeric_fields = _identify_numeric_fields(objects)
                for field_name in numeric_fields:
                    hyps = self._detect_threshold_patterns(
                        objects,
                        type_def.name,
                        field_name,
                    )
                    for h in hyps:
                        await self._hs.put(h)
                        result.hypotheses.append(h)
                        result.proposed += 1

                for i, f1 in enumerate(numeric_fields):
                    for f2 in numeric_fields[i + 1 :]:
                        hyps = self._detect_correlations(
                            objects,
                            type_def.name,
                            f1,
                            f2,
                        )
                        for h in hyps:
                            await self._hs.put(h)
                            result.hypotheses.append(h)
                            result.proposed += 1

                categorical = _identify_categorical_fields(
                    objects,
                    exclude=numeric_fields,
                )
                for field_name in categorical:
                    hyps = self._detect_concentration_patterns(
                        objects,
                        type_def.name,
                        field_name,
                    )
                    for h in hyps:
                        await self._hs.put(h)
                        result.hypotheses.append(h)
                        result.proposed += 1

            except Exception:
                result.errors += 1
                _log.warning(
                    "pattern_scan_failed",
                    type_name=type_def.name,
                    exc_info=True,
                )

        _log.info(
            "pattern_detection_complete",
            proposed=result.proposed,
            errors=result.errors,
            types_scanned=result.types_scanned,
        )
        return result

    # -- Threshold pattern discovery ------------------------------------------

    def _detect_threshold_patterns(
        self,
        objects: list[dict[str, Any]],
        type_name: str,
        field_name: str,
    ) -> list[Hypothesis]:
        """Find values that suggest a threshold-based signal definition."""
        values = _extract_numeric_values(objects, field_name)
        if len(values) < self._min_sample_size:
            return []

        nums = [v for _, v in values]
        mean = sum(nums) / len(nums)
        variance = sum((x - mean) ** 2 for x in nums) / len(nums)
        stddev = math.sqrt(variance) if variance > 0 else 0

        if stddev == 0:
            return []

        outlier_count = sum(
            1 for _, v in values if abs((v - mean) / stddev) >= self._zscore_threshold
        )

        if outlier_count == 0:
            return []

        outlier_pct = outlier_count / len(values)
        proposed_threshold = mean + (self._zscore_threshold * stddev)
        confidence = min(0.95, 0.5 + (outlier_pct * 2) + (len(values) / 1000))

        return [
            Hypothesis(
                hypothesis_id=_hypothesis_id("threshold", f"{type_name}.{field_name}"),
                kind=HypothesisKind.SIGNAL_DEFINITION,
                title=(f"Propose threshold signal for {type_name}.{field_name}"),
                description=(
                    f"{outlier_count} of {len(values)} {type_name} objects have "
                    f"{field_name} values that are statistical outliers "
                    f"(>{self._zscore_threshold}σ from mean). "
                    f"Proposed threshold: {proposed_threshold:.2f}"
                ),
                confidence=round(confidence, 3),
                sample_size=len(values),
                proposed_by="pattern_detector",
                evidence={
                    "type_name": type_name,
                    "field": field_name,
                    "mean": round(mean, 4),
                    "stddev": round(stddev, 4),
                    "outlier_count": outlier_count,
                    "total_count": len(values),
                    "outlier_pct": round(outlier_pct, 4),
                    "proposed_threshold": round(proposed_threshold, 4),
                    "zscore_threshold": self._zscore_threshold,
                },
                proposed_tbox_entry={
                    "kind": "signal_definition",
                    "name": f"{type_name}_{field_name}_outlier",
                    "description": (
                        f"{field_name} exceeds {proposed_threshold:.2f} for {type_name}"
                    ),
                    "entity": type_name,
                    "rule": {
                        "metric": field_name,
                        "condition": "exceeds_threshold",
                        "threshold_value": round(proposed_threshold, 4),
                    },
                },
            )
        ]

    # -- Correlation discovery ------------------------------------------------

    def _detect_correlations(
        self,
        objects: list[dict[str, Any]],
        type_name: str,
        field_a: str,
        field_b: str,
    ) -> list[Hypothesis]:
        """Find correlated numeric fields that suggest causal relationships."""
        pairs: list[tuple[float, float]] = []
        for obj in objects:
            va = obj.get(field_a)
            vb = obj.get(field_b)
            if (
                va is not None
                and vb is not None
                and isinstance(va, (int, float))
                and isinstance(vb, (int, float))
                and not isinstance(va, bool)
                and not isinstance(vb, bool)
            ):
                pairs.append((float(va), float(vb)))

        if len(pairs) < self._min_sample_size:
            return []

        r = _pearson_r(pairs)
        if abs(r) < self._correlation_threshold:
            return []

        direction = "positive" if r > 0 else "negative"
        confidence = min(0.90, abs(r) * 0.8 + (len(pairs) / 2000))

        return [
            Hypothesis(
                hypothesis_id=_hypothesis_id(
                    "correlation",
                    f"{type_name}.{field_a}_{field_b}",
                ),
                kind=HypothesisKind.CAUSAL_CHAIN,
                title=(
                    f"{direction.title()} correlation: "
                    f"{type_name}.{field_a} ↔ {type_name}.{field_b}"
                ),
                description=(
                    f"Strong {direction} correlation (r={r:.3f}) between "
                    f"{field_a} and {field_b} across {len(pairs)} {type_name} objects. "
                    f"When {field_a} {'increases' if r > 0 else 'decreases'}, "
                    f"{field_b} tends to {'increase' if r > 0 else 'decrease'}."
                ),
                confidence=round(confidence, 3),
                sample_size=len(pairs),
                proposed_by="pattern_detector",
                evidence={
                    "type_name": type_name,
                    "field_a": field_a,
                    "field_b": field_b,
                    "pearson_r": round(r, 4),
                    "direction": direction,
                    "sample_size": len(pairs),
                },
                proposed_tbox_entry={
                    "kind": "causal_chain",
                    "cause": f"{type_name}.{field_a}",
                    "effect": f"{type_name}.{field_b}",
                    "description": (
                        f"{direction.title()} correlation (r={r:.3f}) "
                        f"between {field_a} and {field_b}"
                    ),
                },
            )
        ]

    # -- Concentration pattern discovery --------------------------------------

    def _detect_concentration_patterns(
        self,
        objects: list[dict[str, Any]],
        type_name: str,
        field_name: str,
    ) -> list[Hypothesis]:
        """Find concentrated categorical fields that may indicate issues."""
        counts: dict[str, int] = {}
        total = 0

        for obj in objects:
            val = obj.get(field_name)
            if val is not None and isinstance(val, str):
                counts[val] = counts.get(val, 0) + 1
                total += 1

        if total < self._min_sample_size:
            return []

        hypotheses: list[Hypothesis] = []
        for value, count in counts.items():
            pct = count / total
            if pct >= self._concentration_threshold:
                confidence = min(0.85, pct * 0.9 + (total / 5000))
                hypotheses.append(
                    Hypothesis(
                        hypothesis_id=_hypothesis_id(
                            "concentration",
                            f"{type_name}.{field_name}.{value[:20]}",
                        ),
                        kind=HypothesisKind.ANOMALY_PATTERN,
                        title=(
                            f"Concentration: {pct:.0%} of {type_name} have {field_name}='{value}'"
                        ),
                        description=(
                            f"{count} of {total} {type_name} objects have "
                            f"{field_name}='{value}' ({pct:.0%}). This extreme "
                            f"concentration may indicate a data quality issue, "
                            f"a domain constraint worth formalizing, or a signal "
                            f"worth tracking."
                        ),
                        confidence=round(confidence, 3),
                        sample_size=total,
                        proposed_by="pattern_detector",
                        evidence={
                            "type_name": type_name,
                            "field": field_name,
                            "dominant_value": value,
                            "count": count,
                            "total": total,
                            "percentage": round(pct, 4),
                        },
                        proposed_tbox_entry={
                            "kind": "anomaly_pattern",
                            "entity": type_name,
                            "field": field_name,
                            "pattern": f"concentration > {self._concentration_threshold:.0%}",
                        },
                    )
                )
        return hypotheses


# -- Pure functions -----------------------------------------------------------


def _identify_numeric_fields(objects: list[dict[str, Any]]) -> list[str]:
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
    objects: list[dict[str, Any]],
    *,
    exclude: list[str],
) -> list[str]:
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


def _extract_numeric_values(
    objects: list[dict[str, Any]],
    field_name: str,
) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for obj in objects:
        val = obj.get(field_name)
        if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
            values.append((str(obj.get("id", "")), float(val)))
    return values


def _pearson_r(pairs: list[tuple[float, float]]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(pairs)
    if n < 3:
        return 0.0

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / n
    my = sum(ys) / n

    cov = sum((x - mx) * (y - my) for x, y in pairs) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)

    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)
