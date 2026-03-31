"""Embedder implementations.

Supported providers:
  openai   — text-embedding-3-small / text-embedding-3-large (default)
  voyage   — voyage-3 / voyage-3-lite / voyage-finance-2 etc.

NoopEmbedder: deterministic hash-based fallback for tests and offline dev.
              Logs a warning at construction time in non-test environments.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

import structlog

from remi.models.retrieval import Embedder

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
# Voyage AI
# ---------------------------------------------------------------------------


class VoyageEmbedder(Embedder):
    """Embeds text using Voyage AI's embedding API.

    Requires the ``voyageai`` package and a valid VOYAGE_API_KEY.
    Voyage models are retrieval-optimised and support input_type hints.

    Recommended models:
      voyage-3           — 1024-dim, general purpose (default)
      voyage-3-lite      — 512-dim, lower cost / latency
      voyage-finance-2   — 1024-dim, finance domain
    """

    _DIMENSIONS: dict[str, int] = {
        "voyage-3": 1024,
        "voyage-3-lite": 512,
        "voyage-finance-2": 1024,
        "voyage-large-2": 1536,
        "voyage-2": 1024,
    }

    def __init__(
        self,
        model: str = "voyage-3",
        api_key: str | None = None,
        input_type: str = "document",
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("VOYAGE_API_KEY", "")
        self._input_type = input_type
        self._client: Any = None
        self._dimension = self._DIMENSIONS.get(model, 1024)

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import voyageai
            except ImportError as exc:
                raise RuntimeError(
                    "VoyageEmbedder requires the 'voyageai' package. "
                    "Install with: pip install voyageai"
                ) from exc
            self._client = voyageai.AsyncClient(api_key=self._api_key)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        _log.debug("embedding_batch", count=len(texts), model=self._model)
        result = await client.embed(texts, model=self._model, input_type=self._input_type)
        return result.embeddings

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]

    @property
    def dimension(self) -> int:
        return self._dimension


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
