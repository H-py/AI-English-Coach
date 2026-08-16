"""词汇等级中文标签映射。

供服务层与 Agent 工具共用：把 ``word_bank_levels.level`` 的代码值
（``cet4`` / ``cet6`` / ``kaoyan``）映射为中文标签（四级 / 六级 / 考研）。
"""

WORD_LEVEL_LABELS = {
    "cet4": "四级",
    "cet6": "六级",
    "kaoyan": "考研",
}
