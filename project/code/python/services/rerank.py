"""检索结果重排：查询-文档相似度为主，类型加成仅作微调。"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# 类型加成（相对检索分），不再用 ×1.25 这类拍脑袋主权重
TYPE_BONUS: dict[str, float] = {
    "vector": 0.0,
    "graph": 0.05,
    "hybrid": 0.02,
    "subgraph": 0.05,
    "path": 0.08,
    "community": 0.03,
}


def _tokenize(text: str) -> set[str]:
    # 中英混合：中文按字、英文按词
    en = re.findall(r"[A-Za-z0-9_]+", text.lower())
    zh = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    return set(en) | set(zh)


def lexical_similarity(query: str, doc: str) -> float:
    q, d = (query or "").strip(), (doc or "").strip()
    if not q or not d:
        return 0.0
    qt, dt = _tokenize(q), _tokenize(d)
    if qt and dt:
        overlap = len(qt & dt) / max(1, len(qt))
    else:
        overlap = 0.0
    seq = SequenceMatcher(None, q[:200], d[:400]).ratio()
    return 0.6 * overlap + 0.4 * seq


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


async def similarity_scores(
    query: str,
    texts: list[str],
    embeddings: Any | None = None,
) -> list[float]:
    """优先 embedding 余弦；不可用时回退词面相似度。"""
    if embeddings is not None and texts:
        try:
            qv = await embeddings.aembed_query(query)
            dvs = await embeddings.aembed_documents(texts)
            return [_cosine(qv, dv) for dv in dvs]
        except Exception:
            pass
    return [lexical_similarity(query, t) for t in texts]


async def rerank_scored_items(
    query: str,
    items: list[T],
    *,
    get_content: Callable[[T], str],
    get_type: Callable[[T], str],
    get_base_score: Callable[[T], float],
    set_score: Callable[[T, float], None],
    embeddings: Any | None = None,
    content_key_fn: Callable[[T], str] | None = None,
) -> list[T]:
    """
    最终分 = 0.55 * sim(query, doc) + 0.35 * base_score + type_bonus
    再按 content 去重、降序。
    """
    if not items:
        return []
    texts = [get_content(it)[:800] for it in items]
    sims = await similarity_scores(query, texts, embeddings=embeddings)
    for it, sim in zip(items, sims):
        base = float(get_base_score(it) or 0.0)
        bonus = TYPE_BONUS.get(get_type(it), 0.0)
        set_score(it, 0.55 * sim + 0.35 * base + bonus)

    key_fn = content_key_fn or (lambda it: get_content(it)[:100])
    seen: set[str] = set()
    unique: list[T] = []
    for it in sorted(items, key=get_base_score, reverse=True):
        # 上面已写入新 score，用 get_base_score 读回
        k = key_fn(it)
        if k in seen:
            continue
        seen.add(k)
        unique.append(it)
    unique.sort(key=get_base_score, reverse=True)
    return unique
