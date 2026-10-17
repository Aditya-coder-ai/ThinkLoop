"""Unit tests for LLMClient protocol, FakeLLMClient, and AnthropicClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import (
    AnthropicClient,
    FakeLLMClient,
    LLMClient,
    LLMError,
    LLMMessage,
    LLMResult,
    LLMTimeoutError,
    TokenUsage,
)


def test_fake_llm_client_satisfies_protocol() -> None:
    """FakeLLMClient must adhere to the LLMClient protocol."""
    client = FakeLLMClient()
    assert isinstance(client, LLMClient)


@pytest.mark.asyncio
async def test_fake_llm_client_complete() -> None:
    """FakeLLMClient queues and returns LLMResult."""
    client = FakeLLMClient()
    client.queue_completion(
        LLMResult(
            content="Hello learner",
            tool_calls=[{"name": "test_tool", "input": {"arg": 1}}],
            usage=TokenUsage(input_tokens=10, output_tokens=20),
        )
    )

    messages = [LLMMessage(role="user", content="Hi")]
    result = await client.complete(messages=messages, system="You are a tutor")

    assert result.content == "Hello learner"
    assert result.tool_calls == [{"name": "test_tool", "input": {"arg": 1}}]
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 20
    assert len(client.recorded_calls) == 1
    assert client.recorded_calls[0]["messages"] == messages


@pytest.mark.asyncio
async def test_fake_llm_client_stream() -> None:
    """FakeLLMClient streams chunks of text and records call."""
    client = FakeLLMClient()
    client.queue_stream(["Hello", " ", "world", "!"])

    chunks: list[str] = []
    async for chunk in client.stream(messages=[LLMMessage(role="user", content="Hi")]):
        chunks.append(chunk)

    assert "".join(chunks) == "Hello world!"
    assert len(client.recorded_calls) == 1


@pytest.mark.asyncio
async def test_fake_llm_client_timeout_error() -> None:
    """FakeLLMClient can be configured to raise timeout or error."""
    client = FakeLLMClient()
    client.queue_error(LLMTimeoutError("LLM call timed out"))

    with pytest.raises(LLMTimeoutError):
        await client.complete(messages=[LLMMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_anthropic_client_retries_transient_errors() -> None:
    """AnthropicClient retries on rate limits and 5xx errors with exponential backoff."""
    client = AnthropicClient(api_key="test-key", max_retries=3, initial_delay=0.01)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Success after retry", type="text")]
    mock_response.usage = MagicMock(input_tokens=15, output_tokens=25)

    # Simulate 2 transient errors then success
    mock_create = AsyncMock(
        side_effect=[
            Exception("Rate limit 429"),
            Exception("Overloaded 529"),
            mock_response,
        ]
    )

    with patch.object(client, "_raw_create", mock_create):
        result = await client.complete(
            messages=[LLMMessage(role="user", content="Solve x+1=2")],
            system="Tutor",
        )
        assert result.content == "Success after retry"
        assert mock_create.call_count == 3


@pytest.mark.asyncio
async def test_anthropic_client_exhausts_retries() -> None:
    """AnthropicClient raises LLMError when max retries are exhausted."""
    client = AnthropicClient(api_key="test-key", max_retries=2, initial_delay=0.01)

    mock_create = AsyncMock(side_effect=Exception("API service down 500"))

    with patch.object(client, "_raw_create", mock_create):
        with pytest.raises(LLMError):
            await client.complete(
                messages=[LLMMessage(role="user", content="Hello")],
            )
        assert mock_create.call_count == 3  # initial + 2 retries
