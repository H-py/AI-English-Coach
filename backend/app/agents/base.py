"""Agent 基类 —— ReAct 执行循环。

实现 Thought → Action → Observation 的多步推理循环。每个循环步骤：

1. 将当前上下文（系统提示 + 对话历史 + 工具描述 + 上一步 Observation）
   发送给 LLM（非流式调用）。
2. LLM 返回文本，可能包含 ``Thought`` 和 ``Action``（工具调用）或
   ``Final Answer``（最终回答）。
3. 若有 ``Action``，解析工具名和参数，执行工具，将结果作为
   ``Observation`` 追加到上下文。
4. 重复直到 LLM 给出 ``Final Answer`` 或达到最大迭代次数。

所有中间步骤（thinking、tool_call、tool_result）通过异步生成器
yield，供上层封装为 SSE 流推送给前端。最终回答使用流式调用以获得
打字机效果。

ReAct 模式选择理由：DeepSeek 官方文档明确指出 ``deepseek-chat``
模型的 Function Calling "效果不稳定，会出现循环调用、空回复"。
ReAct 通过提示词引导 LLM 输出结构化的 Thought/Action/Observation，
系统侧解析执行，可控性更强，且天然产生可流式的思考文本。
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai.factory import get_llm_provider
from app.core.ai.provider import ChatMessage, LLMProvider
from app.agents.tools.base import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

# ---- Agent 执行循环常量 ----------------------------------------------------

_MAX_ITERATIONS = 6          # 最大推理步数（防止无限循环）
_TEMP_AGENT = 0.6            # Agent 推理温度
_MAX_TOKENS_THINKING = 500   # 单步思考的最大 token
_MAX_TOKENS_ANSWER = 1500    # 最终回答的最大 token


@dataclass
class AgentStep:
    """Agent 执行过程中的单个步骤，用于 SSE 流推送。

    Attributes:
        step_type: 步骤类型 —— ``"thinking"`` / ``"tool_call"`` /
            ``"tool_result"`` / ``"content"`` / ``"done"`` / ``"error"``。
        content: 文本内容（thinking 的思考文本、tool_result 的结果摘要、
            content 的回答分块）。
        tool_name: 工具名称（仅 tool_call 和 tool_result 有值）。
        tool_arguments: 工具参数（仅 tool_call 有值）。
        tool_result_data: 工具返回的原始数据（仅 tool_result 有值，
            用于前端展示）。
    """

    step_type: str
    content: str = ""
    tool_name: str = ""
    tool_arguments: dict = field(default_factory=dict)
    tool_result_data: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Agent 抽象基类。

    子类需实现 :meth:`build_system_prompt` 和 :meth:`get_tool_registry`。
    执行入口为 :meth:`run`，它是一个异步生成器，逐步 yield
    :class:`AgentStep`。

    所有工具的 ``execute`` 方法会接收到 ``db`` 和 ``user_id`` 作为
    隐式上下文参数（由本类注入），确保工具可以安全地访问数据库
    且自动按用户隔离数据。
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        user_id: int,
        article_id: Optional[int] = None,
        history_id: Optional[int] = None,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._user_id = user_id
        self._article_id = article_id
        self._history_id = history_id
        self._provider = provider or get_llm_provider()

    @abstractmethod
    def build_system_prompt(self) -> str:
        """构建 ReAct 系统提示词（含工具描述和输出格式要求）。

        Returns:
            渲染后的系统提示词字符串。
        """
        ...

    @abstractmethod
    def get_tool_registry(self) -> ToolRegistry:
        """返回此 Agent 可用的工具注册表。

        Returns:
            已注册所有工具的 :class:`ToolRegistry` 实例。
        """
        ...

    async def run(
        self,
        user_message: str,
        context_messages: list[ChatMessage],
    ) -> AsyncGenerator[AgentStep, None]:
        """执行 ReAct 推理循环。

        Args:
            user_message: 用户的新消息。
            context_messages: 从记忆系统加载的对话上下文（历史消息，
                不含 system 提示和当前 user 消息）。

        Yields:
            :class:`AgentStep` —— 每个推理步骤、工具调用、工具结果
            和最终回答的分块。
        """
        registry = self.get_tool_registry()
        system_prompt = self.build_system_prompt()

        # 构建 ReAct 对话消息列表。
        messages: list[ChatMessage] = [
            ChatMessage("system", system_prompt),
            *context_messages,
            ChatMessage("user", user_message),
        ]

        for iteration in range(_MAX_ITERATIONS):
            # 非流式调用 LLM 获取当前步的推理结果。
            response = await self._provider.chat(
                messages=messages,
                temperature=_TEMP_AGENT,
                max_tokens=_MAX_TOKENS_THINKING,
            )
            raw_output = response.content.strip()

            # 解析 LLM 输出。
            parsed = self._parse_react_output(raw_output)

            if parsed["type"] == "final_answer":
                # 流式输出最终回答。
                async for chunk in self._stream_final_answer(messages):
                    yield chunk
                yield AgentStep(step_type="done")
                return

            elif parsed["type"] == "action":
                # yield thinking 步骤（如有）。
                if parsed["thought"]:
                    yield AgentStep(
                        step_type="thinking",
                        content=parsed["thought"],
                    )

                # yield tool_call 步骤。
                yield AgentStep(
                    step_type="tool_call",
                    tool_name=parsed["tool_name"],
                    tool_arguments=parsed["tool_args"],
                )

                # 执行工具。
                result = await self._execute_tool(
                    registry, parsed["tool_name"], parsed["tool_args"]
                )

                # yield tool_result 步骤。
                yield AgentStep(
                    step_type="tool_result",
                    tool_name=parsed["tool_name"],
                    content=result.content,
                    tool_result_data=result.data,
                )

                # 将工具调用和结果追加到对话历史，供下一轮 LLM 参考。
                messages.append(ChatMessage("assistant", raw_output))
                messages.append(
                    ChatMessage("user", f"Observation: {result.content}")
                )
            else:
                # 无法解析输出，请求 LLM 直接回答。
                logger.warning(
                    "Agent output could not be parsed (iteration=%d): %s",
                    iteration,
                    raw_output[:200],
                )
                messages.append(ChatMessage("assistant", raw_output))
                messages.append(
                    ChatMessage(
                        "user",
                        "请直接给出最终回答，不要再调用工具。",
                    )
                )

        # 达到最大迭代次数，强制要求最终回答。
        logger.warning(
            "Agent reached max iterations (%d)", _MAX_ITERATIONS
        )
        messages.append(
            ChatMessage(
                "user",
                "已达到最大推理步数。请基于已有信息直接给出最终回答。",
            )
        )
        async for chunk in self._stream_final_answer(messages):
            yield chunk
        yield AgentStep(step_type="done")

    async def _execute_tool(
        self,
        registry: ToolRegistry,
        tool_name: str,
        args: dict,
    ) -> ToolResult:
        """执行指定工具，注入 db 和 user_id 上下文。

        Args:
            registry: 工具注册表。
            tool_name: 要执行的工具名称。
            args: LLM 解析出的工具参数。

        Returns:
            :class:`ToolResult` 工具执行结果。
        """
        tool = registry.get(tool_name)
        if tool is None:
            available = ", ".join(
                t.name for t in registry.all_tools()
            )
            return ToolResult(
                success=False,
                content=f"错误：未知的工具 '{tool_name}'。"
                f"可用工具：{available}",
            )
        try:
            return await tool.execute(
                db=self._db,
                user_id=self._user_id,
                **args,
            )
        except Exception as e:
            logger.exception("Tool execution failed: %s", tool_name)
            return ToolResult(
                success=False, content=f"工具执行出错：{e}"
            )

    def _parse_react_output(self, raw: str) -> dict:
        """解析 LLM 的 ReAct 格式输出。

        期望格式（灵活解析，容错性强）::

            Thought: 我需要先查看用户的词汇收藏情况...
            Action: search_vocabulary
            Action Input: {"keyword": "example"}

        或最终回答::

            Thought: 我已经有足够的信息了。
            Final Answer: 根据你的阅读记录...

        若无法匹配任何格式，则将整个输出视为最终回答（容错降级）。

        Args:
            raw: LLM 的原始输出文本。

        Returns:
            解析结果字典，``type`` 字段为 ``"action"``、
            ``"final_answer"`` 或 ``"unknown"``。
        """
        # 检查是否是最终回答。
        final_match = re.search(
            r"Final\s*Answer\s*[:：]\s*(.*)",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        if final_match:
            return {
                "type": "final_answer",
                "answer": final_match.group(1).strip(),
            }

        # 如果没有 Action 关键字，视为最终回答（容错）。
        if "Action:" not in raw and "Action：" not in raw:
            return {"type": "final_answer", "answer": raw}

        # 解析 Thought。
        thought_match = re.search(
            r"Thought\s*[:：]\s*(.*?)(?=Action|$)",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        thought = (
            thought_match.group(1).strip() if thought_match else ""
        )

        # 解析 Action 名称。
        action_match = re.search(
            r"Action\s*[:：]\s*(\w+)",
            raw,
            re.IGNORECASE,
        )
        if not action_match:
            return {"type": "unknown", "raw": raw}

        tool_name = action_match.group(1).strip()

        # 解析 Action Input（JSON 格式）。
        input_match = re.search(
            r"Action\s*Input\s*[:：]\s*(\{.*?\})",
            raw,
            re.DOTALL | re.IGNORECASE,
        )
        tool_args: dict = {}
        if input_match:
            try:
                tool_args = json.loads(input_match.group(1))
            except json.JSONDecodeError:
                # JSON 解析失败，尝试提取简单的键值对。
                tool_args = {}

        return {
            "type": "action",
            "thought": thought,
            "tool_name": tool_name,
            "tool_args": tool_args,
        }

    async def _stream_final_answer(
        self,
        messages: list[ChatMessage],
    ) -> AsyncGenerator[AgentStep, None]:
        """流式输出最终回答。

        在已有推理上下文的基础上，要求 LLM 用中文给出自然、简洁的
        最终回答，不提及工具调用过程。使用流式调用以获得打字机效果。

        Args:
            messages: 当前完整的对话消息列表。

        Yields:
            ``AgentStep(step_type="content", content=chunk)`` ——
            最终回答的文本分块。
        """
        prompt_messages = list(messages)
        prompt_messages.append(
            ChatMessage(
                "user",
                "请基于以上推理过程和工具结果，用中文给出最终回答。"
                "回答要自然、简洁，不要提及工具调用的过程。",
            )
        )
        async for chunk in self._provider.chat_stream(
            prompt_messages,
            temperature=_TEMP_AGENT,
            max_tokens=_MAX_TOKENS_ANSWER,
        ):
            yield AgentStep(step_type="content", content=chunk)
