"""Framework settings loaded from YAML config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class StateStoreSettings(BaseModel):
    backend: str = "in_memory"
    dsn: str | None = None


class LoggingSettings(BaseModel):
    level: str = "INFO"
    format: str = "structured"


class ExecutionSettings(BaseModel):
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    concurrency_limit: int = 10
    idempotency: bool = True


class ApiSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=list)


class RemiSettings(BaseModel):
    environment: str = "development"
    state_store: StateStoreSettings = Field(default_factory=StateStoreSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)


def load_settings(config_dir: str | Path = "config", env: str = "base") -> RemiSettings:
    config_path = Path(config_dir) / f"{env}.yaml"
    if not config_path.exists():
        return RemiSettings()

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return RemiSettings.model_validate(data)
