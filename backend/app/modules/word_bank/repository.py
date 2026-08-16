"""词库数据访问层。

所有函数均为异步函数，操作共享的 :class:`AsyncSession`。
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.word_bank.models import WordBank, WordBankLevel


async def get_levels_for_words(
    db: AsyncSession, words: list[str]
) -> dict[str, list[str]]:
    """批量返回给定单词（小写原形）所属的等级列表。

    Args:
        db: 当前活跃的异步会话。
        words: 单词（小写原形）列表。

    Returns:
        ``{word: ["cet4", "cet6", ...]}``；未命中的单词不在结果中。
    """
    if not words:
        return {}
    result = await db.execute(
        select(WordBankLevel.level, WordBank.word)
        .join(WordBank, WordBank.id == WordBankLevel.word_id)
        .where(WordBank.word.in_(words))
        .order_by(WordBankLevel.level)
    )
    levels: dict[str, list[str]] = {}
    for level, word in result.all():
        levels.setdefault(word, []).append(level)
    return levels


async def get_word_info(db: AsyncSession, word: str) -> Optional[dict]:
    """返回单个单词（小写原形）的词库信息；不存在时返回 ``None``。"""
    result = await db.execute(select(WordBank).where(WordBank.word == word))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    levels = await get_levels_for_words(db, [word])
    return {
        "word": row.word,
        "phonetic": row.phonetic,
        "meaning": row.meaning,
        "levels": levels.get(word, []),
    }


async def lookup_word(db: AsyncSession, word: str) -> Optional[dict]:
    """查询单词在词库中的信息并标注等级。

    先精确匹配小写原形；未命中时尝试常见屈折变形的原形回退
    （``running`` -> ``run``），以便查词时也能标注变形词的等级。

    Args:
        db: 当前活跃的异步会话。
        word: 待查询的单词（大小写不敏感）。

    Returns:
        词库信息字典（``word``/``phonetic``/``meaning``/``levels``），
        词库中不存在时返回 ``None``。
    """
    normalized = word.strip().lower()
    info = await get_word_info(db, normalized)
    if info is not None:
        return info
    for candidate in _candidate_forms(normalized):
        info = await get_word_info(db, candidate)
        if info is not None:
            return info
    return None


async def get_words_by_level(
    db: AsyncSession, level: str, limit: int = 500
) -> list[str]:
    """返回属于指定等级的词库单词（用于背诵按等级筛选）。"""
    result = await db.execute(
        select(WordBank.word)
        .join(WordBankLevel, WordBankLevel.word_id == WordBank.id)
        .where(WordBankLevel.level == level)
        .limit(limit)
    )
    return list(result.scalars())


async def upsert_word(
    db: AsyncSession,
    word: str,
    phonetic: Optional[str] = None,
    meaning: Optional[str] = None,
    levels: Optional[list[str]] = None,
) -> WordBank:
    """幂等地写入一个单词及其等级归属（供导入脚本使用）。

    单词已存在时补充缺失的音标/释义，并追加未登记的等级，不产生重复。
    """
    normalized = word.strip().lower()
    result = await db.execute(select(WordBank).where(WordBank.word == normalized))
    row = result.scalar_one_or_none()
    if row is None:
        row = WordBank(word=normalized, phonetic=phonetic, meaning=meaning)
        db.add(row)
        await db.flush()
    else:
        if phonetic and not row.phonetic:
            row.phonetic = phonetic
        if meaning and not row.meaning:
            row.meaning = meaning

    for level in dict.fromkeys(levels or []):
        existing = await db.execute(
            select(WordBankLevel).where(
                WordBankLevel.word_id == row.id,
                WordBankLevel.level == level,
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(WordBankLevel(word_id=row.id, level=level))
    await db.flush()
    return row


def _candidate_forms(word: str) -> list[str]:
    """生成可能的原形候选，供词库精确匹配失败时回退（覆盖常见规则变形）。"""
    forms: list[str] = []
    w = word

    # 复数 / 第三人称单数：studies -> study；boxes -> box；runs -> run
    if w.endswith("ies"):
        forms.append(w[:-3] + "y")
    if w.endswith("es"):
        forms.append(w[:-2])
    elif w.endswith("s") and not w.endswith(("ss", "us")):
        forms.append(w[:-1])

    # 过去式 / 过去分词：studied -> study；liked -> like；stopped -> stop
    if w.endswith("ied"):
        forms.append(w[:-3] + "y")
    if w.endswith("ed"):
        base = w[:-2]
        forms.append(base)
        forms.append(base + "e")
        if len(base) >= 3 and base[-1] == base[-2]:
            forms.append(base[:-1])

    # 进行时：running -> run；making -> make
    if w.endswith("ing"):
        base = w[:-3]
        forms.append(base)
        forms.append(base + "e")
        if len(base) >= 3 and base[-1] == base[-2]:
            forms.append(base[:-1])

    # 比较级 / 最高级：easier -> easy；easiest -> easy
    if w.endswith("ier"):
        forms.append(w[:-3] + "y")
    if w.endswith("est"):
        forms.append(w[:-3])
        forms.append(w[:-3] + "y")

    return list(dict.fromkeys(f for f in forms if f and f != w))
