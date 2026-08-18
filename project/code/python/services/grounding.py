"""答案引用可溯源 / 幻觉弱校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence


_SOURCE_PATTERNS = [
    re.compile(r"\[来源\s*(\d+)\s*[:：]?[^\]]*\]"),
    re.compile(r"\[来源\s*[:：]\s*([^\]]+)\]"),
    re.compile(r"\(来源\s*[:：]\s*([^)]+)\)"),
]


@dataclass
class GroundingResult:
    grounded: bool
    notes: list[str]
    cited_ok: int = 0
    cited_bad: int = 0


def check_answer_grounding(answer: str, contexts: Sequence[Any]) -> GroundingResult:
    """
    规则：
    - 无上下文：不允许“有根据”的答案（调用方应拒绝作答）
    - 有上下文：若出现 [来源 N] / [来源: xxx]，必须能对应到 contexts
    - 未出现显式引用时，要求答案与至少一条上下文有词面重叠（弱幻觉检测）
    """
    notes: list[str] = []
    if not contexts:
        return GroundingResult(grounded=False, notes=["no_contexts"])

    sources = []
    for i, c in enumerate(contexts):
        src = getattr(c, "source", None) or (c.get("source") if isinstance(c, dict) else "") or ""
        content = getattr(c, "content", None) or (c.get("content") if isinstance(c, dict) else "") or ""
        sources.append({"index": i + 1, "source": str(src), "content": str(content)})

    text = answer or ""
    cited_ok = cited_bad = 0
    found_cite = False
    for pat in _SOURCE_PATTERNS:
        for m in pat.finditer(text):
            found_cite = True
            token = m.group(1).strip()
            if token.isdigit():
                idx = int(token)
                if 1 <= idx <= len(sources):
                    cited_ok += 1
                else:
                    cited_bad += 1
                    notes.append(f"invalid_source_index:{idx}")
            else:
                if any(token in s["source"] or s["source"] in token for s in sources):
                    cited_ok += 1
                else:
                    cited_bad += 1
                    notes.append(f"unknown_source:{token[:80]}")

    if found_cite and cited_bad > 0:
        return GroundingResult(
            grounded=False,
            notes=notes or ["citation_mismatch"],
            cited_ok=cited_ok,
            cited_bad=cited_bad,
        )

    # 弱重叠：答案字符与任一上下文重叠比例
    ans_chars = {c for c in text if not c.isspace()}
    if len(ans_chars) < 8:
        notes.append("answer_too_short")
        return GroundingResult(grounded=False, notes=notes, cited_ok=cited_ok, cited_bad=cited_bad)

    overlap_ok = False
    for s in sources:
        ctx_chars = {c for c in s["content"] if not c.isspace()}
        if not ctx_chars:
            continue
        inter = len(ans_chars & ctx_chars)
        if inter / max(1, len(ans_chars)) >= 0.08:
            overlap_ok = True
            break
    if not overlap_ok:
        notes.append("low_lexical_overlap_with_contexts")
        return GroundingResult(
            grounded=False,
            notes=notes,
            cited_ok=cited_ok,
            cited_bad=cited_bad,
        )

    if found_cite:
        notes.append("citations_ok")
    else:
        notes.append("overlap_ok_no_explicit_citation")
    return GroundingResult(grounded=True, notes=notes, cited_ok=cited_ok, cited_bad=cited_bad)
