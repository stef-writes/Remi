"""knowledge.entailment — rule-based signal engine.

Submodules:
  engine      — EntailmentEngine (dispatch + run_all)
  base        — EntailmentResult, signal_id helper
  threshold   — EXCEEDS_THRESHOLD unit-level evaluator
  delinquency — manager delinquency rate evaluator
  lease       — lease cliff + policy breach evaluators
  maintenance — maintenance backlog evaluator
  portfolio   — concentration risk + below-percentile evaluators
  trend       — declining periods + consistent direction evaluators
  existence   — EXISTS + IN_LEGAL_TRACK evaluators
"""

from remi.knowledge.entailment.base import EntailmentResult
from remi.knowledge.entailment.engine import EntailmentEngine

__all__ = ["EntailmentEngine", "EntailmentResult"]
