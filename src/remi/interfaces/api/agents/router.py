"""REST endpoints for AI-powered questions and agent discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml
from fastapi import APIRouter, Depends, HTTPException

from remi.interfaces.api.agents.schemas import AskRequest, AskResponse
from remi.interfaces.api.dependencies import get_container
from remi.shared.paths import WORKFLOWS_DIR

if TYPE_CHECKING:
    from remi.infrastructure.config.container import Container

router = APIRouter(prefix="/agents", tags=["ai"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    container: Container = Depends(get_container),
) -> AskResponse:
    try:
        answer, run_id = await container.chat_agent.ask(req.agent, req.question)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    return AskResponse(
        agent=req.agent,
        question=req.question,
        answer=answer,
        run_id=run_id,
    )


@router.get("")
async def list_agents() -> dict[str, Any]:
    """List user-facing agents available for chat.

    Reads metadata from each workflow YAML and filters to those
    marked with ``audience: director`` and ``chat: true``.
    """
    agents = []
    if not WORKFLOWS_DIR.exists():
        return {"agents": agents}

    for app_dir in sorted(WORKFLOWS_DIR.iterdir()):
        app_yaml = app_dir / "app.yaml"
        if not app_yaml.is_file():
            continue
        try:
            with open(app_yaml) as f:
                raw = yaml.safe_load(f)
            meta = raw.get("metadata", {})
            if meta.get("audience") == "system" or meta.get("chat") is False:
                continue
            agents.append({
                "name": meta.get("name", app_dir.name),
                "description": meta.get("description", ""),
                "version": meta.get("version", ""),
                "primary": meta.get("primary", False),
                "tags": meta.get("tags", []),
            })
        except Exception:
            continue

    agents.sort(key=lambda a: (not a["primary"], a["name"]))
    return {"agents": agents}
