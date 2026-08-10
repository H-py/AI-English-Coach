"""Agent 工具包。

所有工具继承 :class:`BaseTool`，通过 :class:`ToolRegistry` 注册后
供 Agent 在 ReAct 推理循环中调用。

工具按领域分组：
    - :mod:`vocabulary` —— 词汇查询与管理。
    - :mod:`reading`    —— 阅读历史与文章内容。
    - :mod:`profile`    —— 用户画像与学习统计。
    - :mod:`memory`     —— 长期记忆检索。
"""
