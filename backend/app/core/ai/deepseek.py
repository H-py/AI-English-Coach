"""DeepSeek LLM provider implementation.

Uses the OpenAI-compatible chat completions API via ``httpx.AsyncClient``
(no OpenAI SDK dependency). Supports both non-streaming (``chat``) and
streaming (``chat_stream``) modes, parsing Server-Sent Events line by line
for the streaming variant.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any, Optional

import httpx

from app.core.ai.provider import ChatMessage, LLMProvider, LLMResponse
from app.core.config import settings
from app.core.exceptions import BizException

# Business error codes for AI-specific failures.
AI_NOT_CONFIGURED_CODE = 50001
AI_API_ERROR_CODE = 50003

# Request timeout in seconds. DeepSeek responses can be slow for long
# generations, so we allow a generous window.
_REQUEST_TIMEOUT = 60.0


class DeepSeekProvider(LLMProvider):
    """LLM provider backed by the DeepSeek chat completions API.

    The provider reads its configuration (API key, base URL, model name)
    from application settings at construction time. All HTTP calls use
    ``httpx.AsyncClient`` with a 60-second timeout.
    """

    def __init__(self) -> None:
        """Initialise the provider with settings from ``app.core.config``."""
        self._api_key: str = settings.DEEPSEEK_API_KEY
        self._base_url: str = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self._model: str = settings.DEEPSEEK_MODEL

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _ensure_configured(self) -> None:
        """Raise a :class:`BizException` if the API key is not set."""
        if not self._api_key:
            raise BizException(
                "AI provider not configured",
                code=AI_NOT_CONFIGURED_CODE,
            )

    def _build_headers(self) -> dict[str, str]:
        """Build the standard request headers with Bearer auth."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
    ) -> dict[str, Any]:
        """Build the JSON request body for the chat completions endpoint."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": msg.role, "content": msg.content} for msg in messages
            ],
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    @staticmethod
    def _raise_api_error(status_code: int, body: str) -> None:
        """Raise a :class:`BizException` for a non-200 API response."""
        raise BizException(
            f"DeepSeek API error: status={status_code}, body={body}",
            code=AI_API_ERROR_CODE,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a non-streaming chat request and return the full response.

        Args:
            messages: The conversation messages.
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Optional maximum number of tokens to generate.
            **kwargs: Additional parameters forwarded to the API (currently
                unused but kept for forward compatibility).

        Returns:
            An :class:`LLMResponse` with the generated content, model name,
            and token-usage statistics.

        Raises:
            BizException: If the API key is not configured (code ``50001``)
                or the API returns a non-200 status (code ``50003``).
        """
        self._ensure_configured()

        url = f"{self._base_url}/chat/completions"
        payload = self._build_payload(
            messages, temperature, max_tokens, stream=False
        )

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                url, headers=self._build_headers(), json=payload
            )

        if response.status_code != 200:
            self._raise_api_error(response.status_code, response.text)

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        model = data.get("model", self._model)

        return LLMResponse(content=content, model=model, usage=usage)

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Send a streaming chat request and yield content deltas.

        The DeepSeek API returns Server-Sent Events: each event is a line
        prefixed with ``data:`` containing a JSON object with a ``choices``
        array. The stream terminates with a ``data: [DONE]`` line.

        Args:
            messages: The conversation messages.
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Optional maximum number of tokens to generate.
            **kwargs: Additional parameters forwarded to the API.

        Yields:
            Content delta strings as they arrive from the API.

        Raises:
            BizException: If the API key is not configured (code ``50001``)
                or the API returns a non-200 status (code ``50003``).
        """
        self._ensure_configured()

        url = f"{self._base_url}/chat/completions"
        payload = self._build_payload(
            messages, temperature, max_tokens, stream=True
        )

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            async with client.stream(
                "POST", url, headers=self._build_headers(), json=payload
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    self._raise_api_error(
                        response.status_code,
                        body.decode("utf-8", errors="replace"),
                    )

                async for line in response.aiter_lines():
                    # Skip blank lines and SSE comments / event markers.
                    if not line or not line.startswith("data:"):
                        continue

                    # Strip the "data:" prefix and surrounding whitespace.
                    data_str = line[len("data:") :].strip()

                    # The stream terminates with a [DONE] sentinel.
                    if data_str == "[DONE]":
                        break

                    # Parse the JSON chunk and extract the content delta.
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        # Skip malformed lines (keep-alives, etc.).
                        continue

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue

                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
