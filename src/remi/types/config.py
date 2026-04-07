"""Configuration schema models — pure Pydantic shapes, no I/O.

These models define the *shape* of settings. They are imported by factories
and services that need typed config. The actual *loading* logic
(YAML, .env, env-var interpolation) stays in ``shell.config.settings``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SecretsSettings(BaseModel):
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    voyage_api_key: str = ""
    database_url: str = ""

    @property
    def has_any_llm_key(self) -> bool:
        return bool(self.openai_api_key or self.anthropic_api_key or self.google_api_key)


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


class LLMSettings(BaseModel):
    """Default LLM provider and model — overridable per-session from the frontend."""

    default_provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-20250514"


class SandboxSettings(BaseModel):
    """Sandbox execution configuration."""

    default_timeout: int = 30
    max_output_bytes: int = 100_000


class EmbeddingsSettings(BaseModel):
    """Embedding provider config — separate from LLM inference config.

    Embeddings require a dedicated API; Claude/Anthropic does not offer one.
    Supported providers: openai, voyage.
    The api_key is resolved at runtime from secrets, not stored here.
    """

    provider: str = "openai"
    model: str = "text-embedding-3-small"
    dimensions: int = 1536


# ---------------------------------------------------------------------------
# Agent-layer store backend selectors
# ---------------------------------------------------------------------------


class VectorStoreSettings(BaseModel):
    """Vector store backend — ``memory`` for dev, ``postgres`` for pgvector."""

    backend: str = "memory"


class MemoryStoreSettings(BaseModel):
    """Episodic memory backend — ``memory`` or ``postgres``."""

    backend: str = "memory"


class TraceStoreSettings(BaseModel):
    """Trace/span persistence — ``memory`` or ``postgres``."""

    backend: str = "memory"


class SessionStoreSettings(BaseModel):
    """Chat session persistence — ``memory`` or ``postgres``."""

    backend: str = "memory"


class RemiSettings(BaseModel):
    environment: str = "development"
    secrets: SecretsSettings = Field(default_factory=SecretsSettings)
    state_store: StateStoreSettings = Field(default_factory=StateStoreSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    vectors: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    memory: MemoryStoreSettings = Field(default_factory=MemoryStoreSettings)
    tracing: TraceStoreSettings = Field(default_factory=TraceStoreSettings)
    sessions: SessionStoreSettings = Field(default_factory=SessionStoreSettings)
