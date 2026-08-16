"""词库导入脚本：把开源分级词表导入 word_bank 表。

用法（在 backend/ 目录下执行）::

    python -m scripts.import_word_bank \\
        --cet4 data/CET4_edited.txt --cet6 data/CET6_edited.txt \\
        --kaoyan data/NPEE_Wordlist.txt

支持两种词表格式（按扩展名自动识别）:

- ``.txt``：每行 ``word [音标] 词性. 中文释义``（mahavivo/english-wordlists
  等开源词表的常见格式；自动跳过标题、空行与分组字母行）。
- ``.json``：数组 ``[{"name": "abandon", "ukphone": "...", "trans": "..."}]``
  或字典 ``{"abandon": {"phonetic": "...", "meaning": "..."}}``，
  键名兼容 name/word、ukphone/phonetic、trans/translation/meaning。

等级值与 ``word_bank_levels.level`` 一一对应；同一单词出现在多个词表时，
会同时登记多个等级。脚本幂等：重复执行不会产生重复数据。
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.modules.word_bank.models import WordBank, WordBankLevel

_WORD_RE = re.compile(r"^[a-z][a-z'-]*$")
# 文本格式：word [音标] 词性. 中文释义（音标可有可无）
_TEXT_LINE_RE = re.compile(
    r"^(?P<word>[a-zA-Z][a-zA-Z'-]*)\s*(?:\[(?P<phonetic>[^\]]*)\])?\s+(?P<rest>.+)$"
)

# 支持的等级（与 word_bank_levels.level 一致）；新增等级在此追加即可。
LEVELS = ("cet4", "cet6", "kaoyan")


def _normalize_word(word: str) -> Optional[str]:
    """规范化为小写原形；含空格/数字等非纯单词形式丢弃。"""
    normalized = word.strip().lower()
    return normalized if _WORD_RE.match(normalized) else None


def _extract(entry: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    word = entry.get("name") or entry.get("word")
    phonetic = entry.get("ukphone") or entry.get("phonetic")
    meaning = entry.get("trans") or entry.get("translation") or entry.get("meaning")
    # qwerty-learner 等来源的 trans 可能是字符串列表，拼接为一段文本。
    if isinstance(meaning, list):
        meaning = "；".join(str(m) for m in meaning if m)
    return word, phonetic, meaning


def _load_txt(path: Path) -> list[tuple[Optional[str], Optional[str], Optional[str]]]:
    """解析 ``word [音标] 词性. 释义`` 文本词表。"""
    entries: list[tuple[Optional[str], Optional[str], Optional[str]]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _TEXT_LINE_RE.match(line.strip())
            if not m:
                continue  # 标题、空行、分组字母等
            entries.append(
                (
                    m.group("word").lower(),
                    m.group("phonetic") or None,
                    m.group("rest").strip(),
                )
            )
    return entries


def _load_entries(path: Path) -> list[tuple[Optional[str], Optional[str], Optional[str]]]:
    """读取词表文件，统一为 (word, phonetic, meaning) 元组列表。"""
    if path.suffix.lower() != ".json":
        return _load_txt(path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    entries: list[tuple[Optional[str], Optional[str], Optional[str]]] = []
    if isinstance(raw, dict):
        for word, info in raw.items():
            if isinstance(info, dict):
                entries.append(_extract(info))
            else:
                entries.append((word, None, None))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                entries.append(_extract(item))
    return entries


async def _import_level(
    db, level: str, path: Path, existing: dict[str, WordBank]
) -> int:
    """把单个等级的词表 upsert 进词库，返回该等级导入的去重词数。"""
    entries = _load_entries(path)
    new_words: list[WordBank] = []
    seen: set[str] = set()

    for word, phonetic, meaning in entries:
        normalized = _normalize_word(word or "")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        row = existing.get(normalized)
        if row is None:
            row = WordBank(word=normalized, phonetic=phonetic, meaning=meaning)
            existing[normalized] = row
            new_words.append(row)
        else:
            if phonetic and not row.phonetic:
                row.phonetic = phonetic
            if meaning and not row.meaning:
                row.meaning = meaning

    # flush 新单词以获取自增 id，再批量登记等级
    db.add_all(new_words)
    await db.flush()

    level_rows = [
        {"word_id": existing[w].id, "level": level} for w in seen
    ]
    if level_rows:
        await db.execute(
            pg_insert(WordBankLevel).values(level_rows).on_conflict_do_nothing()
        )
    return len(seen)


async def main() -> None:
    parser = argparse.ArgumentParser(description="导入分级词库到 word_bank")
    for level in LEVELS:
        parser.add_argument(f"--{level}", type=Path, help=f"{level} 词表 JSON 路径")
    args = parser.parse_args()

    provided = {lv: getattr(args, lv) for lv in LEVELS if getattr(args, lv) is not None}
    if not provided:
        print(
            "未提供任何词表文件。示例：\n"
            "  python -m scripts.import_word_bank "
            "--cet4 data/cet4.json --cet6 data/cet6.json --kaoyan data/kaoyan.json"
        )
        sys.exit(1)
    for path in provided.values():
        if not path.exists():
            print(f"文件不存在：{path}")
            sys.exit(1)

    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        existing: dict[str, WordBank] = {}
        result = await db.execute(select(WordBank))
        for row in result.scalars():
            existing[row.word] = row

        total = 0
        for level, path in provided.items():
            count = await _import_level(db, level, path, existing)
            total += count
            print(f"{level}: 导入 {count} 个单词")
        await db.commit()
        print(f"完成，共处理 {total} 个单词（含跨等级重复）")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
