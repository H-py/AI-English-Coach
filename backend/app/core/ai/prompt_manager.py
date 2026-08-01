"""Prompt template manager.

Loads ``.md`` prompt templates from the ``backend/prompts/`` directory and
renders them with `Jinja2 <https://jinja.palletsprojects.com/>`_ variable
substitution.

Raw template text is cached in memory after the first read; rendered output
is never cached because each call may supply different variables.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment

from app.core.exceptions import BizException

# Business error code: a requested prompt template file does not exist.
PROMPT_NOT_FOUND_CODE = 50002

# Resolve the prompts directory relative to this file:
#   backend/app/core/ai/prompt_manager.py  (4 levels up to reach backend/)
_PROMPTS_DIR: Path = (
    Path(__file__).resolve().parent.parent.parent.parent / "prompts"
)

# A shared Jinja2 environment. ``autoescape`` is disabled because prompt
# templates are plain text/markdown, not HTML. ``undefined`` is left as the
# default (``Undefined``) so that missing variables render as empty strings
# or can use Jinja2's ``default()`` filter, rather than raising.
_env = Environment(
    autoescape=False,
    keep_trailing_newline=True,
)

# Cache of raw (unrendered) template text keyed by the relative template path
# (without extension), e.g. ``"system/coach"``.
_raw_cache: dict[str, str] = {}


def _load_raw(template_path: str) -> str:
    """Load and cache the raw text of a prompt template.

    Args:
        template_path: A path relative to ``prompts/`` **without** the
            ``.md`` extension, e.g. ``"system/coach"`` or
            ``"reading/article_summary"``.

    Returns:
        The raw template text (cached after first read).

    Raises:
        BizException: If the template file does not exist
            (code ``50002``).
    """
    if template_path in _raw_cache:
        return _raw_cache[template_path]

    file_path = _PROMPTS_DIR / f"{template_path}.md"
    if not file_path.is_file():
        raise BizException(
            f"prompt template not found: {template_path}",
            code=PROMPT_NOT_FOUND_CODE,
        )

    raw = file_path.read_text(encoding="utf-8")
    _raw_cache[template_path] = raw
    return raw


def load_prompt(template_path: str, **variables: Any) -> str:
    """Load a prompt template and render it with the given variables.

    Args:
        template_path: A path relative to ``prompts/`` **without** the
            ``.md`` extension, e.g. ``"reading/article_summary"``.
        **variables: Variables passed to the Jinja2 template for rendering.

    Returns:
        The rendered prompt string.

    Raises:
        BizException: If the template file does not exist (code ``50002``).
    """
    raw = _load_raw(template_path)
    template = _env.from_string(raw)
    return template.render(**variables)


def load_system_prompt(name: str) -> str:
    """Load a system-role prompt template from ``prompts/system/{name}.md``.

    System prompts typically do not require variable substitution; any
    Jinja2 expressions they contain should use the ``default()`` filter so
    they render gracefully without variables.

    Args:
        name: The template name (without extension), e.g. ``"coach"``.

    Returns:
        The rendered system prompt string.

    Raises:
        BizException: If the template file does not exist (code ``50002``).
    """
    return load_prompt(f"system/{name}")


def load_reading_prompt(name: str, **variables: Any) -> str:
    """Load a reading-related prompt template from ``prompts/reading/{name}.md``.

    Args:
        name: The template name (without extension), e.g.
            ``"article_summary"``.
        **variables: Variables passed to the Jinja2 template for rendering.

    Returns:
        The rendered prompt string.

    Raises:
        BizException: If the template file does not exist (code ``50002``).
    """
    return load_prompt(f"reading/{name}", **variables)
