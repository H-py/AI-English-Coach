"""阅读教练 Agent —— 第一个具体的 Agent 实现。

继承自 :class:`~app.agents.base.BaseAgent`，使用 ReAct 推理模式。
集成了词汇、阅读、画像和记忆四类共 9 个工具，使 Agent 能够全面了解
用户的学习状况并给出个性化的英语阅读辅导。

工具列表：
    - ``search_vocabulary``: 搜索收藏的单词。
    - ``get_word_detail``: 获取单个单词详情。
    - ``get_all_vocabulary``: 获取全部收藏单词（按掌握程度分组）。
    - ``get_reading_history``: 获取阅读历史。
    - ``get_article_content``: 获取文章内容。
    - ``get_sentence_collection``: 获取收藏的句子。
    - ``get_user_profile``: 获取用户学习画像。
    - ``get_learning_stats``: 获取学习统计。
    - ``search_memories``: 搜索长期记忆。
"""

from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.tools.base import ToolRegistry
from app.agents.tools.memory import SearchMemoriesTool
from app.agents.tools.profile import GetLearningStatsTool, GetUserProfileTool
from app.agents.tools.reading import (
    GetArticleContentTool,
    GetReadingHistoryTool,
    GetSentenceCollectionTool,
)
from app.agents.tools.vocabulary import (
    GetAllVocabularyTool,
    GetWordDetailTool,
    SearchVocabularyTool,
)
from app.core.ai.prompt_manager import load_prompt

# ReAct 推理的最大迭代步数。
_MAX_ITERATIONS = 6


class ReadingCoachAgent(BaseAgent):
    """阅读教练 Agent。

    集成了词汇、阅读、画像和记忆四类工具，能够根据用户的学习数据
    提供个性化的英语阅读辅导。通过 ReAct 提示词模板引导 LLM 进行
    多步推理，在需要时调用工具获取数据，最终给出自然的回答。
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        user_id: int,
        article_id: Optional[int] = None,
        history_id: Optional[int] = None,
    ) -> None:
        """初始化阅读教练 Agent。

        调用父类构造函数完成基础设置，然后构建工具注册表，注册全部
        8 个工具。

        Args:
            db: 当前请求的异步数据库会话。
            redis: 共享的异步 Redis 客户端。
            user_id: 当前用户 id。
            article_id: 用户正在阅读的文章 id（可选）。
            history_id: 当前阅读会话的历史记录 id（可选）。
        """
        super().__init__(db, redis, user_id, article_id, history_id)

        # 构建工具注册表，注册全部工具。
        self._registry = ToolRegistry()
        # 词汇收藏工具。
        self._registry.register(SearchVocabularyTool())
        self._registry.register(GetWordDetailTool())
        self._registry.register(GetAllVocabularyTool())
        # 阅读数据工具。
        self._registry.register(GetReadingHistoryTool())
        self._registry.register(GetArticleContentTool())
        self._registry.register(GetSentenceCollectionTool())
        # 用户画像工具。
        self._registry.register(GetUserProfileTool())
        self._registry.register(GetLearningStatsTool())
        # 记忆检索工具。
        self._registry.register(SearchMemoriesTool())

    def get_tool_registry(self) -> ToolRegistry:
        """返回此 Agent 的工具注册表。

        Returns:
            已注册全部工具的 :class:`ToolRegistry` 实例。
        """
        return self._registry

    def build_system_prompt(self) -> str:
        """构建 ReAct 系统提示词。

        使用 ``agents/reading_coach_react`` 模板，注入工具描述列表
        和最大迭代步数。

        Returns:
            渲染后的系统提示词字符串。
        """
        return load_prompt(
            "agents/reading_coach_react",
            tools=self._registry.to_prompt_string(),
            max_iterations=_MAX_ITERATIONS,
        )
