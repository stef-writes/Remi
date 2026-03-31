"""Request/response schemas for the AI agents endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    agent: str = "director"


class AskResponse(BaseModel):
    agent: str
    question: str
    answer: str | None
    run_id: str
