"""application/tools — domain service functions used by API routes.

With the CLI-first architecture, agent tool providers (``WorkflowToolProvider``,
``ActionToolProvider``, ``SearchToolProvider``) have been removed. The agent
accesses the platform via ``remi`` CLI commands, not function-calling tools.

Remaining modules:

- ``assertions.py`` — ``_assert_fact`` and ``_add_context`` service functions
  consumed by the intelligence API routes.
- ``documents.py`` — ``DocumentToolProvider`` retained for the ingestion
  pipeline's internal use.
- ``ingestion.py`` — ``register_ingestion_tools`` for pipeline tool setup.
"""

from remi.application.tools.ingestion import register_ingestion_tools

__all__ = [
    "register_ingestion_tools",
]
