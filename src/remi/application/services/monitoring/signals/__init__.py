"""Signals category — RE entailment evaluators.

Each module evaluates a specific domain condition (delinquency, lease
cliff, maintenance backlog, etc.) and produces ``Signal`` instances.
The ``EntailmentEngine`` dispatches rule definitions to the appropriate
evaluator.  ``build_signal_pipeline`` assembles the full composite
producer used at runtime.
"""
