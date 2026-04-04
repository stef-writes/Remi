"""Shared API response models used across multiple routers."""

from __future__ import annotations

from pydantic import BaseModel


class DeletedResponse(BaseModel, frozen=True):
    deleted: bool = True


class UpdatedResponse(BaseModel, frozen=True):
    id: str
    name: str
