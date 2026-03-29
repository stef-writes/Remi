"""Embedder implementations.

OpenAIEmbedder: production embedder using OpenAI's text-embedding API.
NoopEmbedder:   zero-vector fallback for tests and environments without API keys.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

import structlog

from remi.domain.retrieval.ports import Embedder

_log = structlog.get_logger(__name__)

_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_OPENAI_DIMENSION = 1536


class OpenAIEmbedder(Embedder):
    """Embeds text using OpenAI's embedding API.

    Requires the ``openai`` package and a valid ``OPENAI_API_KEY``.
    Batches requests for efficiency (OpenAI supports up to 2048 inputs).
    """

    def __init__(
        self,
        model: str = _OPENAI_DEFAULT_MODEL,
        api_key: str | None = None,
        dimensions: int = _OPENAI_DIMENSION,
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

        vectors = [item.embedding for item in response.data]
        return vectors

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]

    @property
    def dimension(self) -> int:
        return self._dimensions


class NoopEmbedder(Embedder):
    """Deterministic pseudo-embedder for tests and offline development.

    Produces reproducible vectors derived from text hashing — not
    semantically meaningful, but structurally valid and deterministic.
    """

    def __init__(self, dimension: int = 128) -> None:
        self._dimension = dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    async def embed_one(self, text: str) -> list[float]:
        return self._hash_embed(text)

    @property
    def dimension(self) -> int:
        return self._dimension

    def _hash_embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        raw = []
        while len(raw) < self._dimension:
            raw.extend(b / 255.0 * 2 - 1 for b in h)
            h = hashlib.sha256(h).digest()
        raw = raw[: self._dimension]
        norm = math.sqrt(sum(x * x for x in raw))
        if norm > 0:
            raw = [x / norm for x in raw]
        return raw
