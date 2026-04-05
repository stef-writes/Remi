"""Embedder implementations and factory.

Supported providers:
  openai   — text-embedding-3-small / text-embedding-3-large (default)

NoopEmbedder: deterministic hash-based fallback for tests and offline dev.
              Logs a warning at construction time in non-test environments.

``build_embedder`` selects the right implementation from settings.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

import structlog

from remi.agent.vectors.types import Embedder
from remi.types.config import EmbeddingsSettings, SecretsSettings

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIEmbedder(Embedder):
    """Embeds text using OpenAI's embedding API.

    Requires the ``openai`` package and a valid API key.
    Batches requests for efficiency (OpenAI supports up to 2048 inputs per call).
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        dimensions: int = 1536,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._dimensions = dimensions
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "OpenAIEmbedder requires the 'openai' package. "
                    "Install with: pip install 'remi[openai]'"
                ) from exc
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        cleaned = [t[:8191] for t in texts]
        _log.debug("embedding_batch", count=len(cleaned), model=self._model)
        response = await client.embeddings.create(
            input=cleaned,
            model=self._model,
            dimensions=self._dimensions,
        )
        return [item.embedding for item in response.data]

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]

    @property
    def dimension(self) -> int:
        return self._dimensions


# ---------------------------------------------------------------------------
# Noop (tests / offline dev)
# ---------------------------------------------------------------------------


class NoopEmbedder(Embedder):
    """Deterministic pseudo-embedder for tests and offline development.

    Produces reproducible vectors derived from text hashing — not semantically
    meaningful, but structurally valid and deterministic. Logs a warning at
    construction time so it is obvious when real embeddings are not being used.
    """

    def __init__(self, dimension: int = 128, *, silent: bool = False) -> None:
        self._dimension = dimension
        if not silent:
            _log.warning(
                "noop_embedder_active",
                message=(
                    "No embedding provider is configured — using NoopEmbedder. "
                    "Semantic search will not return meaningful results. "
                    "Set REMI_EMBEDDINGS_PROVIDER and the corresponding API key "
                    "to enable real embeddings."
                ),
            )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    async def embed_one(self, text: str) -> list[float]:
        return self._hash_embed(text)

    @property
    def dimension(self) -> int:
        return self._dimension

    def _hash_embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        raw: list[float] = []
        while len(raw) < self._dimension:
            raw.extend(b / 255.0 * 2 - 1 for b in h)
            h = hashlib.sha256(h).digest()
        raw = raw[: self._dimension]
        norm = math.sqrt(sum(x * x for x in raw))
        if norm > 0:
            raw = [x / norm for x in raw]
        return raw


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_embedder(cfg: EmbeddingsSettings, secrets: SecretsSettings) -> Embedder:
    """Select and construct an embedder from settings."""
    provider = cfg.provider.lower()

    if provider == "openai" and secrets.openai_api_key:
        return OpenAIEmbedder(
            model=cfg.model,
            api_key=secrets.openai_api_key,
            dimensions=cfg.dimensions,
        )

    return NoopEmbedder()
