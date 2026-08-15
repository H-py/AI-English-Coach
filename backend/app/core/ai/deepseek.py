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
# 用户自定义模型配置调用失败（区别于默认 provider 的 50003）。
USER_AI_CONFIG_ERROR_CODE = 50004

# 请求超时（秒）。DeepSeek 在长篇生成时响应可能较慢，因此我们留出充裕的时间窗口。
_REQUEST_TIMEOUT = 60.0


class DeepSeekProvider(LLMProvider):
    """基于 DeepSeek 聊天补全 API 的 LLM 提供方。

    该提供方在构造时读取其配置（API key、base URL、模型名）。未显式传入
    时回落到应用配置（``settings``）中的默认值。支持用户自定义模型：
    当 ``from_user_config=True`` 时，API 调用失败会抛出带具体原因的
    ``BizException``（错误码 ``50004``），而不会静默回退到默认模型。
    所有 HTTP 调用都使用 ``httpx.AsyncClient``，超时时间为 60 秒。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        from_user_config: bool = False,
    ) -> None:
        """使用显式参数或应用配置初始化提供方。

        Args:
            api_key: API Key；为 ``None`` 时使用 ``settings.DEEPSEEK_API_KEY``。
            base_url: Base URL；为 ``None`` 时使用 ``settings.DEEPSEEK_BASE_URL``。
            model: 模型名；为 ``None`` 时使用 ``settings.DEEPSEEK_MODEL``。
            from_user_config: 是否来自用户自定义配置。为 True 时错误会
                以友好中文提示（错误码 ``50004``）抛出。
        """
        self._api_key = api_key if api_key is not None else settings.DEEPSEEK_API_KEY
        self._base_url = (
            base_url if base_url is not None else settings.DEEPSEEK_BASE_URL
        ).rstrip("/")
        self._model = model if model is not None else settings.DEEPSEEK_MODEL
        self._from_user_config = from_user_config

    @property
    def model(self) -> str:
        """当前提供方使用的模型名（供缓存键与展示使用）。"""
        return self._model

    # ------------------------------------------------------------------ #
    # 内部辅助方法
    # ------------------------------------------------------------------ #

    def _ensure_configured(self) -> None:
        """若未设置 API key，则抛出 :class:`BizException`。"""
        if not self._api_key:
            if self._from_user_config:
                raise BizException(
                    "你的模型配置缺少 API Key，请到“模型配置”页面补全后再试",
                    code=USER_AI_CONFIG_ERROR_CODE,
                )
            raise BizException(
                "AI provider not configured",
                code=AI_NOT_CONFIGURED_CODE,
            )

    def _raise_api_error(self, status_code: int, body: str) -> None:
        """针对非 200 的 API 响应抛出 :class:`BizException`。

        用户自定义配置失败时给出指明具体字段的友好中文提示
        （错误码 ``50004``）；默认提供方保持原有错误码 ``50003``。
        """
        if self._from_user_config:
            raise self._map_api_error(status_code, body)
        raise BizException(
            f"DeepSeek API error: status={status_code}, body={body}",
            code=AI_API_ERROR_CODE,
        )

    def _raise_connect_error(self, exc: Exception) -> None:
        """针对连接层异常抛出带友好提示的 :class:`BizException`。

        连接错误（无法连接 / 连接中断 / 流式回复被截断）统一转成可读的
        中文提示，避免底层英文错误直接暴露给用户。用户自定义配置失败时
        给出指向 Base URL 的提示（``50004``）；默认提供方给出通用提示
        （``50003``）。原始异常由调用方记录日志，便于排查。
        """
        if self._from_user_config:
            raise BizException(
                f"无法连接到模型服务 {self._base_url} —— 请检查 Base URL 是否正确、网络是否可达",
                code=USER_AI_CONFIG_ERROR_CODE,
            )
        raise BizException(
            "模型服务连接异常，AI 回复未完整生成，请稍后重试",
            code=AI_API_ERROR_CODE,
        )

    def _map_api_error(self, status_code: int, body: str) -> BizException:
        """把 HTTP 状态码映射为指明具体原因的用户配置错误提示。

        Returns:
            带友好中文消息、错误码 ``50004`` 的 :class:`BizException`。
        """
        if status_code == 401:
            msg = "API 密钥无效（401）—— 请检查你的 API Key 是否正确"
        elif status_code == 403:
            msg = "API 密钥无权限（403）—— 请检查 API Key 对该服务是否可用"
        elif status_code == 404:
            msg = (
                f"Base URL 路径可能错误（404）—— {self._base_url}/chat/completions "
                "不存在，请确认 Base URL 是否包含正确的 API 根路径"
            )
        elif status_code == 400:
            msg = (
                f"模型名可能错误（400）—— “{self._model}” 在 {self._base_url} "
                f"上不可用。服务端响应：{body[:200]}"
            )
        elif status_code == 429:
            msg = "请求过于频繁（429）—— 请稍后重试或检查配额"
        else:
            msg = (
                f"模型服务返回错误（{status_code}）—— 响应：{body[:300]}"
            )
        return BizException(msg, code=USER_AI_CONFIG_ERROR_CODE)

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

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.post(
                    url, headers=self._build_headers(), json=payload
                )
        except httpx.TransportError as exc:
            self._raise_connect_error(exc)

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

        try:
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
        except httpx.TransportError as exc:
            self._raise_connect_error(exc)
