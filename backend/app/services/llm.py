"""LLM Client Protocol, Anthropic Client, and Deterministic Fake Client."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMMessage(BaseModel):
    """Normalized chat message for LLM completion and streaming."""

    role: Literal["user", "assistant", "system"]
    content: str


class TokenUsage(BaseModel):
    """Token usage breakdown for an LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0


class LLMResult(BaseModel):
    """Result of an LLM completion call."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class LLMError(Exception):
    """Base exception for LLM operations."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM call times out."""


@runtime_checkable
class LLMClient(Protocol):
    """Protocol defining LLM interaction capabilities."""

    async def complete(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> LLMResult:
        """Execute structured/unstructured completion call."""
        ...

    def stream(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream reply tokens asynchronously."""
        ...


class FakeLLMClient:
    """Scriptable deterministic fake LLM client for testing and CI."""

    def __init__(self) -> None:
        self._completion_queue: list[LLMResult] = []
        self._stream_queue: list[list[str]] = []
        self._error_queue: list[Exception] = []
        self._stream_error_queue: list[Exception] = []
        self._chunk_delay: float = 0.0
        self.recorded_calls: list[dict[str, Any]] = []

    def set_chunk_delay(self, delay: float) -> None:
        """Set an artificial delay between streamed chunks."""
        self._chunk_delay = delay

    def queue_completion(self, result: LLMResult) -> None:
        """Queue a result for complete()."""
        self._completion_queue.append(result)

    def queue_stream(self, chunks: list[str]) -> None:
        """Queue a sequence of string chunks for stream()."""
        self._stream_queue.append(chunks)

    def queue_error(self, exc: Exception) -> None:
        """Queue an exception to be raised on next call."""
        self._error_queue.append(exc)

    def queue_stream_error(self, exc: Exception) -> None:
        """Queue an exception specifically to be raised during stream()."""
        self._stream_error_queue.append(exc)

    async def complete(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> LLMResult:
        self.recorded_calls.append(
            {
                "type": "complete",
                "messages": messages,
                "system": system,
                "tools": tools,
                "tool_choice": tool_choice,
                "model": model,
            }
        )
        if self._error_queue:
            raise self._error_queue.pop(0)
        if self._completion_queue:
            return self._completion_queue.pop(0)
        return LLMResult(
            content="Fake default completion",
            usage=TokenUsage(input_tokens=5, output_tokens=5),
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        self.recorded_calls.append(
            {
                "type": "stream",
                "messages": messages,
                "system": system,
                "model": model,
            }
        )
        if self._stream_error_queue:
            raise self._stream_error_queue.pop(0)
        if self._error_queue:
            raise self._error_queue.pop(0)

        chunks = (
            self._stream_queue.pop(0) if self._stream_queue else ["Default ", "fake ", "stream"]
        )
        for chunk in chunks:
            if self._chunk_delay > 0:
                await asyncio.sleep(self._chunk_delay)
            yield chunk


class AnthropicClient:
    """Production async Anthropic client with retries, backoff, and caching support."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-3-5-sonnet-latest",
        timeout: float = 30.0,
        max_retries: int = 3,
        initial_delay: float = 0.5,
    ) -> None:
        self._api_key = api_key or ""
        self._default_model = default_model
        self._timeout = timeout
        self._max_retries = max_retries
        self._initial_delay = initial_delay

    async def _raw_create(self, **kwargs: Any) -> Any:
        """Execute raw Anthropic API call."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=self._timeout)
        return await client.messages.create(**kwargs)

    async def _call_with_retry(self, **kwargs: Any) -> Any:
        """Execute API call with bounded retries and exponential backoff."""
        delay = self._initial_delay
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await self._raw_create(**kwargs)
            except Exception as e:
                last_exc = e
                err_str = str(e).lower()
                is_transient = any(
                    code in err_str
                    for code in ["429", "500", "502", "503", "504", "529", "overloaded", "rate"]
                )
                if not is_transient or attempt >= self._max_retries:
                    break
                logger.warning(
                    "Anthropic API call failed (attempt %d/%d). Retrying in %.2fs: %s",
                    attempt + 1,
                    self._max_retries,
                    delay,
                    type(e).__name__,
                )
                await asyncio.sleep(delay)
                delay *= 2.0

        if last_exc:
            raise LLMError(f"Anthropic API call failed after retries: {last_exc}") from last_exc
        raise LLMError("Unknown error during Anthropic API call")

    async def complete(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> LLMResult:
        """Call Anthropic API messages.create with retry and tool handling."""
        model_name = model or self._default_model
        formatted_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": formatted_messages,
            "max_tokens": 1024,
        }

        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        try:
            response = await asyncio.wait_for(
                self._call_with_retry(**kwargs),
                timeout=self._timeout,
            )
        except TimeoutError as e:
            raise LLMTimeoutError(f"Anthropic API call timed out after {self._timeout}s") from e

        content_text = ""
        tool_calls: list[dict[str, Any]] = []

        for block in getattr(response, "content", []):
            if getattr(block, "type", "") == "text":
                content_text += getattr(block, "text", "")
            elif getattr(block, "type", "") == "tool_use":
                tool_calls.append(
                    {
                        "name": getattr(block, "name", ""),
                        "input": getattr(block, "input", {}),
                    }
                )

        usage = TokenUsage(
            input_tokens=getattr(response.usage, "input_tokens", 0)
            if hasattr(response, "usage")
            else 0,
            output_tokens=getattr(response.usage, "output_tokens", 0)
            if hasattr(response, "usage")
            else 0,
        )

        return LLMResult(
            content=content_text,
            tool_calls=tool_calls,
            usage=usage,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        system: str | None = None,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream reply tokens using Anthropic AsyncAnthropic client."""
        import anthropic

        model_name = model or self._default_model
        formatted_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=self._timeout)

        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": formatted_messages,
            "max_tokens": 1024,
        }
        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        try:
            async with client.messages.stream(**kwargs) as stream_resp:
                async for text in stream_resp.text_stream:
                    yield text
        except TimeoutError as e:
            raise LLMTimeoutError(f"Anthropic streaming timed out after {self._timeout}s") from e
        except Exception as e:
            raise LLMError(f"Anthropic streaming failed: {e}") from e
