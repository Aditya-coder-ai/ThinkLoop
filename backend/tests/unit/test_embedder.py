"""Unit tests for Embedder interface, FakeEmbedder, and HttpEmbedder."""

import math

import httpx
import pytest


def test_fake_embedder_deterministic_and_unit_norm() -> None:
    from app.content.embedder import FakeEmbedder

    dim = 1024
    embedder = FakeEmbedder(dimension=dim)

    text = "An object remains at rest unless acted on by an external force."
    v1 = embedder.embed(text)
    v2 = embedder.embed(text)

    # Determinism
    assert v1 == v2
    assert len(v1) == dim

    # Unit norm
    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-5

    # Different text produces different vectors
    v3 = embedder.embed("A completely different topic about electromagnetism.")
    assert v1 != v3


def test_fake_embedder_batch() -> None:
    from app.content.embedder import FakeEmbedder

    embedder = FakeEmbedder(dimension=512)
    texts = ["text1", "text2", "text3"]
    vectors = embedder.embed_batch(texts)

    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 512
        assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-5


@pytest.mark.asyncio
async def test_http_embedder_calls_mock_endpoint() -> None:
    from app.content.embedder import HttpEmbedder

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        data = request.read().decode("utf-8")
        assert "Newton" in data
        return httpx.Response(
            status_code=200,
            json={"data": [{"embedding": [0.1] * 1024}]},
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        embedder = HttpEmbedder(
            endpoint_url="https://api.example.com/v1/embeddings",
            api_key="test-key",
            model="text-embedding-3-large",
            dimension=1024,
            client=client,
        )
        vec = await embedder.embed_async("Newton's Laws")
        assert len(vec) == 1024
        assert vec[0] == 0.1


@pytest.mark.asyncio
async def test_http_embedder_retries_on_server_error() -> None:
    from app.content.embedder import HttpEmbedder

    attempts = 0

    async def mock_retry_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            return httpx.Response(status_code=503, json={"error": "Service Unavailable"})
        return httpx.Response(
            status_code=200,
            json={"data": [{"embedding": [0.5] * 1024}]},
        )

    transport = httpx.MockTransport(mock_retry_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        embedder = HttpEmbedder(
            endpoint_url="https://api.example.com/v1/embeddings",
            api_key="test-key",
            model="text-embedding-3-large",
            dimension=1024,
            max_retries=3,
            client=client,
        )
        vec = await embedder.embed_async("Gravity")
        assert attempts == 2
        assert vec[0] == 0.5
