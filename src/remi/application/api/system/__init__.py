"""System — agents, documents, reports, usage, realtime.

Platform capabilities: agent chat, document ingestion, report loading,
LLM usage tracking, and WebSocket event broadcasting.
"""

from remi.application.api.system.agents import router as agents_router
from remi.application.api.system.documents import router as documents_router
from remi.application.api.system.realtime import router as realtime_router
from remi.application.api.system.seed import router as reports_router
from remi.application.api.system.usage import router as usage_router

__all__ = [
    "agents_router",
    "documents_router",
    "realtime_router",
    "reports_router",
    "usage_router",
]
