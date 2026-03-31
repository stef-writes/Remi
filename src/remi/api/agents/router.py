"""REST endpoints for agent discovery and model listing."""

from __future__ import annotations

from typing import Any

import structlog
import yaml
from fastapi import APIRouter, Depends

from remi.api.dependencies import get_provider_factory, get_settings
from remi.config.settings import RemiSettings
from remi.llm.factory import LLMProviderFactory
from remi.observability.events import Event
from remi.shared.paths import AGENTS_DIR

logger = structlog.get_logger("remi.api.agents")

router = APIRouter(prefix="/agents", tags=["ai"])


@router.get("/models")
async def list_models(
    settings: RemiSettings = Depends(get_settings),
    factory: LLMProviderFactory = Depends(get_provider_factory),
) -> dict[str, Any]:
    """Return available LLM providers/models and current defaults."""
    available = factory.available()

    provider_models: dict[str, list[str]] = {
        "openai": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o3-mini",
            "o4-mini",
        ],
        "anthropic": [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20251001",
        ],
        "gemini": [
            "gemini-2.5-pro-preview-05-06",
            "gemini-2.5-flash-preview-04-17",
            "gemini-2.0-flash",
        ],
    }

    return {
        "default_provider": settings.llm.default_provider,
        "default_model": settings.llm.default_model,
        "providers": [
            {
                "name": name,
                "available": name in available,
                "models": provider_models.get(name, []),
            }
            for name in ["openai", "anthropic", "gemini"]
        ],
    }


@router.get("")
async def list_agents() -> dict[str, Any]:
    """List user-facing agents available for chat.

    Reads metadata from each agent's app.yaml and filters to those
    marked with ``audience: director`` and ``chat: true``.
    """
    agents = []
    if not AGENTS_DIR.exists():
        return {"agents": agents}

    for app_dir in sorted(AGENTS_DIR.iterdir()):
        app_yaml = app_dir / "app.yaml"
        if not app_yaml.is_file():
            continue
        try:
            with open(app_yaml) as f:
                raw = yaml.safe_load(f)
            meta = raw.get("metadata", {})
            if meta.get("audience") == "system" or meta.get("chat") is False:
                continue
            agents.append(
                {
                    "name": meta.get("name", app_dir.name),
                    "description": meta.get("description", ""),
                    "version": meta.get("version", ""),
                    "primary": meta.get("primary", False),
                    "tags": meta.get("tags", []),
                }
            )
        except Exception:
            logger.warning(Event.AGENT_CONFIG_INVALID, agent_dir=app_dir.name, exc_info=True)
            continue

    agents.sort(key=lambda a: (not a["primary"], a["name"]))
    return {"agents": agents}
