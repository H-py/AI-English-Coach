"""词库模块：分级单词知识库（四级 / 六级 / 考研等，可拓展）。

词库为只读参考数据，供查词标注词汇等级、agent 查词工具与生词本展示使用。
"""

from app.modules.word_bank.models import WordBank, WordBankLevel, WordLevel

__all__ = ["WordBank", "WordBankLevel", "WordLevel"]
