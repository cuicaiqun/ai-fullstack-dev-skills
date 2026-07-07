#!/usr/bin/env python3
"""Skill 质量评分器。

用法：
  python tools/skill_quality_score.py

输出：
  SKILL_QUALITY_REPORT.md
"""
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / 'skills').glob('**/SKILL.md'))
CHECKS = [
    ('trigger', ['触发场景', '启动本 Skill']),
    ('inputs', ['必要输入', '优先向我索取']),
    ('outputs', ['标准输出', '至少输出']),
    ('sop', ['执行流程 SOP', '执行流程']),
    ('quality_gate', ['质量门禁']),
    ('anti_patterns', ['反模式', '禁止事项', 'must_not_do']),
    ('example_prompt', ['可复制使用提示词', '示例输入']),
    ('verification', ['验证命令', '未实际验证']),
    ('next_skills', ['后续 Skill', '下一步']),
    ('risk_mode', ['风险等级', '执行模式']),
]

def score(text: str):
    got = []
    for key, words in CHECKS:
        ok = any(w in text for w in words)
        got.append((key, ok))
    return sum(1 for _, ok in got if ok), got

rows = []
for p in SKILLS:
    text = p.read_text(encoding='utf-8')
    pts, got = score(text)
    missing = [k for k, ok in got if not ok]
    rows.append((pts, str(p.relative_to(ROOT)), missing, len(text)))

rows.sort(key=lambda x: (x[0], x[1]))
md = ['# Skill 质量评分报告', '', f'生成日期：{date.today().isoformat()}', '', f'共扫描 `{len(rows)}` 个 Skill。满分 10 分。', '', '| 分数 | 文件 | 缺失项 | 字符数 |', '|---:|---|---|---:|']
for pts, rel, missing, length in rows:
    md.append(f'| {pts}/10 | `{rel}` | {", ".join(missing) if missing else "-"} | {length} |')

(ROOT / 'SKILL_QUALITY_REPORT.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
print(f'Generated SKILL_QUALITY_REPORT.md for {len(rows)} skills')
