"""Framework settings loaded from YAML config files and environment variables.

Settings are assembled from three sources (later wins):
1. YAML config file (config/base.yaml by default)
2. Environment variables (loaded from .env if present)
3. Explicit overrides passed to load_settings()

Secrets (API keys, DSNs) are never stored in YAML — they come from env vars
or .env files and are mapped into ``SecretsSettings``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# .env file loader (no external deps)
# ---------------------------------------------------------------------------

def _load_dotenv(path: Path) -> None:
    """Parse a .env file and inject into os.environ (does not override existing vars)."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# ${VAR} interpolation in YAML values
# ---------------------------------------------------------------------------

_ENV_RE = re.compile(r"\$\{(\w+)\}")


def _interpolate(data: Any) -> Any:
    """Recursively resolve ${VAR} references in YAML values from os.environ."""
    if isinstance(data, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), data)
    if isinstance(data, dict):
        return {k: _interpolate(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_interpolate(v) for v in data]
    return data


# ---------------------------------------------------------------------------
# Settings models
# ---------------------------------------------------------------------------

class SecretsSettings(BaseModel):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    database_url: str = ""


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
    secrets: SecretsSettings = Field(default_factory=SecretsSettings)
    state_store: StateStoreSettings = Field(default_factory=StateStoreSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_ENV_VAR_MAP: dict[str, str] = {
    "OPENAI_API_KEY": "openai_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "GOOGLE_API_KEY": "google_api_key",
    "DATABASE_URL": "database_url",
    "APPOS_DATABASE_URL": "database_url",
}


def load_settings(
    config_dir: str | Path = "config",
    env: str = "base",
    dotenv_path: str | Path | None = ".env",
) -> RemiSettings:
    # 1. Load .env into os.environ (won't override existing vars)
    if dotenv_path:
        _load_dotenv(Path(dotenv_path))

    # 2. Load YAML config and interpolate ${VAR} references
    config_path = Path(config_dir) / f"{env}.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = _interpolate(yaml.safe_load(f) or {})
    else:
        data = {}

    # 3. Populate secrets from env vars
    secrets: dict[str, str] = {}
    for env_var, field_name in _ENV_VAR_MAP.items():
        value = os.environ.get(env_var, "")
        if value:
            secrets[field_name] = value
    if secrets:
        data.setdefault("secrets", {}).update(secrets)

    return RemiSettings.model_validate(data)
