"""DeepSeek LLM 提供方实现。

通过 ``httpx.AsyncClient`` 使用 OpenAI 兼容的聊天补全 API（不依赖 OpenAI
SDK）。同时支持非流式（``chat``）和流式（``chat_stream``）两种模式，
流式模式下会逐行解析 Server-Sent Events。
"""

import json
from collections.abc import AsyncGenerator
from typing import Any, Optional

import httpx

from app.core.ai.provider import ChatMessage, LLMProvider, LLMResponse
from app.core.config import settings
from app.core.exceptions import BizException

# AI 特有失败的业务错误码。
AI_NOT_CONFIGURED_CODE = 50001
AI_API_ERROR_CODE = 50003

# 请求超时（秒）。DeepSeek 在长篇生成时响应可能较慢，因此我们留出充裕的时间窗口。
_REQUEST_TIMEOUT = 60.0


class DeepSeekProvider(LLMProvider):
    """基于 DeepSeek 聊天补全 API 的 LLM 提供方。

    该提供方在构造时从应用配置中读取其配置（API key、base URL、模型名）。
    所有 HTTP 调用都使用 ``httpx.AsyncClient``，超时时间为 60 秒。
    """

    def __init__(self) -> None:
        """使用 ``app.core.config`` 中的配置初始化提供方。"""
        self._api_key: str = settings.DEEPSEEK_API_KEY
        self._base_url: str = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self._model: str = settings.DEEPSEEK_MODEL

    # ------------------------------------------------------------------ #
    # 内部辅助方法
    # ------------------------------------------------------------------ #

    def _ensure_configured(self) -> None:
        """若未设置 API key，则抛出 :class:`BizException`。"""
        if not self._api_key:
            raise BizException(
                "AI provider not configured",
                code=AI_NOT_CONFIGURED_CODE,
            )

    def _build_headers(self) -> dict[str, str]:
        """构建带 Bearer 认证的标准请求头。"""
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
        """构建聊天补全端点的 JSON 请求体。"""
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
        """针对非 200 的 API 响应抛出 :class:`BizException`。"""
        raise BizException(
            f"DeepSeek API error: status={status_code}, body={body}",
            code=AI_API_ERROR_CODE,
        )

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送非流式聊天请求并返回完整响应。

        Args:
            messages: 对话消息列表。
            temperature: 采样温度（0.0 - 2.0）。
            max_tokens: 可选，生成 token 的最大数量。
            **kwargs: 转发给 API 的附加参数（当前未使用，但保留以备前向兼容）。

        Returns:
            一个 :class:`LLMResponse`，包含生成内容、模型名以及 token 用量统计。

        Raises:
            BizException: 若 API key 未配置（code ``50001``）或 API 返回非 200
                状态码（code ``50003``）。
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
        """发送流式聊天请求并产出内容增量。

        DeepSeek API 返回 Server-Sent Events：每个事件是一行以 ``data:``
        为前缀的文本，包含一个带 ``choices`` 数组的 JSON 对象。流以
        ``data: [DONE]`` 行结束。

        Args:
            messages: 对话消息列表。
            temperature: 采样温度（0.0 - 2.0）。
            max_tokens: 可选，生成 token 的最大数量。
            **kwargs: 转发给 API 的附加参数。

        Yields:
            从 API 到达的内容增量字符串。

        Raises:
            BizException: 若 API key 未配置（code ``50001``）或 API 返回非 200
                状态码（code ``50003``）。
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
                    # 跳过空行和 SSE 注释 / 事件标记。
                    if not line or not line.startswith("data:"):
                        continue

                    # 去掉 "data:" 前缀及两侧空白。
                    data_str = line[len("data:") :].strip()

                    # 流以 [DONE] 哨兵结束。
                    if data_str == "[DONE]":
                        break

                    # 解析 JSON 数据块并提取内容增量。
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        # 跳过格式错误的行（keep-alive 等）。
                        continue

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue

                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
