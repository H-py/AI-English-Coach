"""提示词模板管理器。

从 ``backend/prompts/`` 目录加载 ``.md`` 提示词模板，并使用
`Jinja2 <https://jinja.palletsprojects.com/>`_ 进行变量替换。

原始模板文本在首次读取后缓存在内存中；渲染后的输出从不缓存，因为每次
调用可能传入不同的变量。
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment

from app.core.exceptions import BizException

# 业务错误码：请求的提示词模板文件不存在。
PROMPT_NOT_FOUND_CODE = 50002

# 相对于本文件解析提示词目录：
#   backend/app/core/ai/prompt_manager.py（向上 4 级到达 backend/）
_PROMPTS_DIR: Path = (
    Path(__file__).resolve().parent.parent.parent.parent / "prompts"
)

# 共享的 Jinja2 环境。禁用 ``autoescape``，因为提示词模板是纯文本/markdown，
# 而非 HTML。``undefined`` 保持默认（``Undefined``），使缺失的变量渲染为
# 空字符串或可使用 Jinja2 的 ``default()`` 过滤器，而不是抛出异常。
_env = Environment(
    autoescape=False,
    keep_trailing_newline=True,
)

# 原始（未渲染）模板文本的缓存，以相对模板路径（不含扩展名）为键，
# 例如 ``"system/coach"``。
_raw_cache: dict[str, str] = {}


def _load_raw(template_path: str) -> str:
    """加载并缓存提示词模板的原始文本。

    Args:
        template_path: 相对于 ``prompts/`` 的路径，**不带** ``.md`` 扩展名，
            例如 ``"system/coach"`` 或 ``"reading/article_summary"``。

    Returns:
        原始模板文本（首次读取后缓存）。

    Raises:
        BizException: 若模板文件不存在（code ``50002``）。
    """
    if template_path in _raw_cache:
        return _raw_cache[template_path]

    file_path = _PROMPTS_DIR / f"{template_path}.md"
    if not file_path.is_file():
        raise BizException(
            f"提示词模板不存在：{template_path}",
            code=PROMPT_NOT_FOUND_CODE,
        )

    raw = file_path.read_text(encoding="utf-8")
    _raw_cache[template_path] = raw
    return raw


def load_prompt(template_path: str, **variables: Any) -> str:
    """加载提示词模板并用给定变量进行渲染。

    Args:
        template_path: 相对于 ``prompts/`` 的路径，**不带** ``.md`` 扩展名，
            例如 ``"reading/article_summary"``。
        **variables: 传给 Jinja2 模板用于渲染的变量。

    Returns:
        渲染后的提示词字符串。

    Raises:
        BizException: 若模板文件不存在（code ``50002``）。
    """
    raw = _load_raw(template_path)
    template = _env.from_string(raw)
    return template.render(**variables)


def load_system_prompt(name: str) -> str:
    """从 ``prompts/system/{name}.md`` 加载系统角色提示词模板。

    系统提示词通常不需要变量替换；其中包含的任何 Jinja2 表达式应使用
    ``default()`` 过滤器，以便在无变量时也能正常渲染。

    Args:
        name: 模板名（不含扩展名），例如 ``"coach"``。

    Returns:
        渲染后的系统提示词字符串。

    Raises:
        BizException: 若模板文件不存在（code ``50002``）。
    """
    return load_prompt(f"system/{name}")


def load_reading_prompt(name: str, **variables: Any) -> str:
    """从 ``prompts/reading/{name}.md`` 加载阅读相关提示词模板。

    Args:
        name: 模板名（不含扩展名），例如 ``"article_summary"``。
        **variables: 传给 Jinja2 模板用于渲染的变量。

    Returns:
        渲染后的提示词字符串。

    Raises:
        BizException: 若模板文件不存在（code ``50002``）。
    """
    return load_prompt(f"reading/{name}", **variables)
