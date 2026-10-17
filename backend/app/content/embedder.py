"""Embedding interfaces and implementations.

Provides an Embedder protocol with:
- FakeEmbedder: Deterministic, unit-norm hash-based vectors for tests & CI.
- HttpEmbedder: Provider-agnostic remote HTTP embeddings client.
"""

import hashlib
import math
import random
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import httpx


@runtime_checkable
class Embedder(Protocol):
    """Protocol defining vector embedding generation."""

    @property
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...

    def embed(self, text: str) -> list[float]:
        """Synchronously compute embedding for a single text."""
        ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Synchronously compute embeddings for multiple texts."""
        ...

    async def embed_async(self, text: str) -> list[float]:
        """Asynchronously compute embedding for a single text."""
        ...

    async def embed_batch_async(self, texts: Sequence[str]) -> list[list[float]]:
        """Asynchronously compute embeddings for multiple texts."""
        ...


class FakeEmbedder:
    """Deterministic, hash-based unit-norm embedder for tests and local dev."""

    def __init__(self, dimension: int = 1024, dim: int | None = None) -> None:
        self._dimension = dim if dim is not None else dimension
        self.call_count = 0

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        self.call_count += 1
        # Deterministic seed from sha256 hash of text
        text_hash = hashlib.sha256(text.encode("utf-8")).digest()
        seed_val = int.from_bytes(text_hash[:8], byteorder="big")
        rng = random.Random(seed_val)

        # Generate Gaussian random vector
        raw_vec = [rng.gauss(0.0, 1.0) for _ in range(self._dimension)]

        # L2 normalize to unit length
        norm = math.sqrt(sum(x * x for x in raw_vec))
        if norm == 0:
            raw_vec[0] = 1.0
            return raw_vec
        return [x / norm for x in raw_vec]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    async def embed_async(self, text: str) -> list[float]:
        return self.embed(text)

    async def embed_batch_async(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_batch(texts)


class HttpEmbedder:
    """Provider-agnostic HTTP embeddings client with retry resilience."""

    def __init__(
        self,
        endpoint_url: str,
        api_key: str,
        model: str,
        dimension: int = 1024,
        max_retries: int = 3,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
        dim: int | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.model = model
        self._dimension = dim if dim is not None else dimension
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self._client = client

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        """Synchronous wrapper for embed_async."""
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.embed_async(text))
        else:
            raise RuntimeError(
                "Synchronous embed() cannot be called inside an active async event loop; "
                "use embed_async."
            )

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.embed_batch_async(texts))
        else:
            raise RuntimeError(
                "Synchronous embed_batch() cannot be called inside an active async event loop; "
                "use embed_batch_async."
            )

    async def _post_with_retry(self, payload: dict[str, object]) -> dict[str, object]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        should_close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds)
            should_close = True

        try:
            last_exc: Exception | None = None
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        self.endpoint_url,
                        headers=headers,
                        json=payload,
                    )
                    if response.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"Server error {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError(
                            "Expected JSON dictionary response from embeddings endpoint"
                        )
                    return data
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    last_exc = exc
                    if attempt == self.max_retries - 1:
                        raise
            if last_exc:
                raise last_exc
            raise RuntimeError("Failed to obtain embeddings response after retries")
        finally:
            if should_close and client is not None:
                await client.aclose()

    async def embed_async(self, text: str) -> list[float]:
        payload: dict[str, object] = {
            "model": self.model,
            "input": text,
            "dimensions": self._dimension,
        }
        data = await self._post_with_retry(payload)
        items = data.get("data")
        if not isinstance(items, list) or len(items) == 0:
            raise ValueError(f"Malformed embeddings response: {data}")
        first_item = items[0]
        if not isinstance(first_item, dict) or "embedding" not in first_item:
            raise ValueError(f"Missing 'embedding' key in response item: {first_item}")
        emb = first_item["embedding"]
        if not isinstance(emb, list):
            raise ValueError("Expected list of floats for embedding vector")
        return [float(x) for x in emb]

    async def embed_batch_async(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, object] = {
            "model": self.model,
            "input": list(texts),
            "dimensions": self._dimension,
        }
        data = await self._post_with_retry(payload)
        items = data.get("data")
        if not isinstance(items, list) or len(items) != len(texts):
            raise ValueError(f"Mismatched batch size in embeddings response: {data}")
        result: list[list[float]] = []
        for item in items:
            if not isinstance(item, dict) or "embedding" not in item:
                raise ValueError(f"Malformed batch item: {item}")
            result.append([float(x) for x in item["embedding"]])
        return result
