"""智能体（Agent）模块。

提供基于 ReAct 提示词模式的多步推理智能体框架，支持工具调用和
流式思考过程展示。

核心组件：
    - :class:`BaseAgent` —— Agent 基类，实现 ReAct 执行循环。
    - :class:`BaseTool` —— 工具抽象基类。
    - :class:`ReadingCoachAgent` —— 首个具体 Agent（阅读教练）。
"""
