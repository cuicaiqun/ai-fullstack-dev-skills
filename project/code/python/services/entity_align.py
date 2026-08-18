"""实体对齐：别名表 + 规范化 + 字符串/向量相似度合并。"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

_SUFFIX_RE = re.compile(
    r"(股份有限公司|有限责任公司|有限公司|集团公司|集团|公司|股份)$"
)


def normalize_entity_name(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"\s+", "", n)
    n = _SUFFIX_RE.sub("", n)
    return n.casefold()


def load_alias_map(raw: str | None = None) -> dict[str, str]:
    text = (raw if raw is not None else settings.entity_alias_map) or ""
    text = text.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return {str(k).strip(): str(v).strip() for k, v in data.items() if str(k).strip()}
    except json.JSONDecodeError:
        logger.warning("ENTITY_ALIAS_MAP is not valid JSON; ignoring")
    return {}


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_entity_name(a), normalize_entity_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
        return 0.9 + 0.1 * (len(shorter) / max(1, len(longer)))
    return SequenceMatcher(None, na, nb).ratio()


def build_canonical_map(
    names: list[str],
    *,
    alias_map: dict[str, str] | None = None,
    threshold: float | None = None,
) -> dict[str, str]:
    """返回 original_name -> canonical_name。"""
    thr = threshold if threshold is not None else settings.entity_similarity_threshold
    aliases = alias_map if alias_map is not None else load_alias_map()
    mapping: dict[str, str] = {}
    # 先应用显式别名
    for n in names:
        if n in aliases:
            mapping[n] = aliases[n]

    # 聚类：按出现顺序选较长名为 canonical
    unresolved = [n for n in names if n not in mapping]
    clusters: list[list[str]] = []
    for n in unresolved:
        placed = False
        for cluster in clusters:
            rep = cluster[0]
            if name_similarity(n, rep) >= thr:
                cluster.append(n)
                placed = True
                break
        if not placed:
            clusters.append([n])

    for cluster in clusters:
        canonical = max(cluster, key=lambda x: (len(x), x))
        for n in cluster:
            mapping[n] = canonical
    return mapping
