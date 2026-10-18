"""Unit tests for GeminiClient LLM service and get_llm_client dependency."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from app.api.deps import get_llm_client
from app.config import Settings
from app.services.llm import (
    AnthropicClient,
    FakeLLMClient,
    GeminiClient,
    LLMError,
    LLMMessage,
    LLMTimeoutError,
)


def test_gemini_client_initialization():
    client = GeminiClient(api_key="fake-key")
    assert client._api_key == "fake-key"
    assert client.fast_model == "gemini-3.8-flash"
    assert client.strong_model == "gemini-3.8-flash"


def test_gemini_client_convert_schema():
    client = GeminiClient(api_key="fake-key")
    anthropic_schema = {
        "type": "object",
        "description": "Test schema",
        "properties": {
            "understanding": {
                "type": "string",
                "enum": ["correct", "incorrect"],
            },
            "confidence": {"type": "number"},
            "misconception_id": {"type": ["string", "null"]},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["understanding"],
    }
    converted = client._convert_schema_to_gemini(anthropic_schema)
    assert converted["type"] == "OBJECT"
    assert converted["description"] == "Test schema"
    assert converted["properties"]["understanding"]["type"] == "STRING"
    assert converted["properties"]["understanding"]["enum"] == ["correct", "incorrect"]
    assert converted["properties"]["confidence"]["type"] == "NUMBER"
    assert converted["properties"]["misconception_id"]["type"] == "STRING"
    assert converted["properties"]["tags"]["type"] == "ARRAY"
    assert converted["properties"]["tags"]["items"]["type"] == "STRING"
    assert converted["required"] == ["understanding"]

    # Non-dict fallback
    assert client._convert_schema_to_gemini("not-a-dict") == "not-a-dict"


def test_gemini_client_format_messages():
    client = GeminiClient(api_key="fake-key")
    messages = [
        LLMMessage(role="system", content="System instruction from message"),
        LLMMessage(role="user", content="Hello"),
        LLMMessage(role="assistant", content="Hi! How can I help?"),
    ]
    sys_inst, contents = client._format_messages_for_gemini(messages, system=None)
    assert sys_inst == {"parts": [{"text": "System instruction from message"}]}
    assert len(contents) == 2
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Hello"
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["text"] == "Hi! How can I help?"

    # Empty messages fallback
    sys_inst_empty, contents_empty = client._format_messages_for_gemini([])
    assert sys_inst_empty is None
    assert len(contents_empty) == 1
    assert contents_empty[0]["parts"][0]["text"] == "Hello"


@pytest.mark.asyncio
async def test_gemini_client_complete_success():
    client = GeminiClient(api_key="fake-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Here is some feedback."},
                        {
                            "functionCall": {
                                "name": "submit_diagnosis",
                                "args": {"understanding": "correct"},
                            }
                        },
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 42,
            "candidatesTokenCount": 18,
        },
    }

    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=mock_resp)
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        result = await client.complete(
            messages=[LLMMessage(role="user", content="Test prompt")],
            system="System prompt",
            tools=[{
                "name": "submit_diagnosis",
                "description": "Submit diagnosis",
                "input_schema": {"type": "object", "properties": {"understanding": {"type": "string"}}},
            }],
            tool_choice={"type": "auto"},
        )

    assert result.content == "Here is some feedback."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "submit_diagnosis"
    assert result.tool_calls[0]["input"] == {"understanding": "correct"}
    assert result.usage.input_tokens == 42
    assert result.usage.output_tokens == 18


@pytest.mark.asyncio
async def test_gemini_client_complete_http_error():
    client = GeminiClient(api_key="fake-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"

    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(return_value=mock_resp)
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(LLMError, match="Gemini API error"):
            await client.complete(messages=[LLMMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_gemini_client_complete_timeout():
    client = GeminiClient(api_key="fake-key")
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(LLMTimeoutError, match="timed out"):
            await client.complete(messages=[LLMMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_gemini_client_complete_generic_exception():
    client = GeminiClient(api_key="fake-key")
    mock_http_client = AsyncMock()
    mock_http_client.post = AsyncMock(side_effect=RuntimeError("Connection lost"))
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(LLMError, match="Gemini request failed"):
            await client.complete(messages=[LLMMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_gemini_client_stream_success():
    client = GeminiClient(api_key="fake-key")

    chunk1 = json.dumps({"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]})
    chunk2 = json.dumps({"candidates": [{"content": {"parts": [{"text": "learner!"}]}}]})

    async def mock_aiter_lines():
        yield f"data: {chunk1}"
        yield "data:   "
        yield "data: invalid-json"
        yield f"data: {chunk2}"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = mock_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_http_client = AsyncMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        tokens = []
        async for token in client.stream(messages=[LLMMessage(role="user", content="Hi")]):
            tokens.append(token)

    assert "".join(tokens) == "Hello learner!"


@pytest.mark.asyncio
async def test_gemini_client_stream_http_error():
    client = GeminiClient(api_key="fake-key")
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.aread = AsyncMock(return_value=b"Forbidden")

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_http_client = AsyncMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(LLMError, match="Gemini streaming error"):
            async for _ in client.stream(messages=[LLMMessage(role="user", content="Hi")]):
                pass


@pytest.mark.asyncio
async def test_gemini_client_stream_timeout():
    client = GeminiClient(api_key="fake-key")
    mock_http_client = AsyncMock()
    mock_http_client.stream = MagicMock(side_effect=httpx.TimeoutException("Stream timeout"))
    mock_http_client.__aenter__.return_value = mock_http_client
    mock_http_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_http_client):
        with pytest.raises(LLMTimeoutError, match="streaming timed out"):
            async for _ in client.stream(messages=[LLMMessage(role="user", content="Hi")]):
                pass


def test_get_llm_client_dependency():
    test_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="test",
    )
    assert isinstance(get_llm_client(test_settings), FakeLLMClient)

    anthropic_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="development",
        anthropic_api_key="sk-ant-test",
    )
    client_ant = get_llm_client(anthropic_settings)
    assert isinstance(client_ant, AnthropicClient)

    gemini_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="development",
        anthropic_api_key=None,
        gemini_api_key="gemini-test-key",
    )
    client_gem = get_llm_client(gemini_settings)
    assert isinstance(client_gem, GeminiClient)

    none_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="development",
        anthropic_api_key=None,
        gemini_api_key=None,
    )
    assert isinstance(get_llm_client(none_settings), FakeLLMClient)

