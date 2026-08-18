#!/usr/bin/env python3
"""Scan project/ progress and recommend a specialist role + next skills.

Usage:
  python assess_progress.py [workspace_or_pack_root]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


DOMAIN_GLOBS: dict[str, list[str]] = {
    "requirements": [
        "docs/01_requirements/**",
        "docs/**/*PRD*",
        "docs/**/requirements*.md",
        "docs/**/prd*.md",
    ],
    "product_design": [
        "docs/02_product_design/**",
        "docs/**/page_structure.md",
        "docs/**/wireframe*.md",
    ],
    "architecture": [
        "docs/03_architecture/**",
        "CLAUDE.md",
        "docs/**/architecture*.md",
        "项目介绍/架构设计详解.md",
    ],
    "database": [
        "sql/**/*.sql",
        "docs/04_database/**",
        "**/migrations/**/*.sql",
    ],
    "api": [
        "docs/05_api/**",
        "**/*openapi*.{yaml,yml,json,md}",
        "code/python/api/**/*.py",
        "backend/**/api/**/*.py",
        "backend/**/*router*.py",
    ],
    "backend": [
        "backend/**",
        "code/python/api/**/*.py",
        "code/python/agents/**/*.py",
        "code/python/services/**/*.py",
    ],
    "frontend": [
        "frontend/**",
        "code/python/static/**",
        "**/src/App.{tsx,jsx,vue}",
        "**/pages.json",
    ],
    "testing": [
        "tests/**",
        "docs/07_testing/**",
        "code/python/tests/**/*.py",
        "code/python/scripts/run_unit_tests.sh",
        "**/pytest.ini",
    ],
    "security": [
        "docs/08_security/**",
        "**/secrets_guard.py",
        "**/upload_security.py",
        "**/auth/**/*.py",
        "code/python/tests/test_auth*.py",
        "code/python/tests/test_qa_acl.py",
    ],
    "deployment": [
        "docs/09_deployment/**",
        "**/docker-compose*.yml",
        "**/Dockerfile",
        "code/tls/**",
        "scripts/backup.sh",
        "code/scripts/backup.sh",
        "code/python/scripts/check_p0_3_deploy.py",
    ],
}

STAGE_ORDER = [
    "requirements",
    "product_design",
    "architecture",
    "database",
    "api",
    "backend",
    "frontend",
    "testing",
    "security",
    "deployment",
]

STAGE_TO_ROLE = {
    "requirements": "product_manager",
    "product_design": "product_designer",
    "architecture": "architect",
    "database": "dba",
    "api": "api_designer",
    "backend": "backend_engineer",
    "frontend": "frontend_engineer",
    "testing": "qa_engineer",
    "security": "security_engineer",
    "deployment": "devops_engineer",
    "launch_hardening": "devops_engineer",
    "iteration": "iteration_pm",
}

STAGE_TO_SKILLS = {
    "requirements": [
        "core.project_context_collector",
        "requirements.idea_to_requirements",
        "requirements.mvp_scope_definition",
    ],
    "product_design": [
        "product_design.information_architecture",
        "product_design.user_flow_design",
        "product_design.interaction_state_spec",
    ],
    "architecture": [
        "architecture.tech_stack_selection",
        "architecture.architecture_blueprint",
        "architecture.repo_structure_standard",
    ],
    "database": [
        "database.table_design",
        "database.sql_generation",
        "database.migration_seed_plan",
    ],
    "api": [
        "api.api_design_orchestrator",
        "api.openapi_spec_generator",
        "api.endpoint_contract_design",
    ],
    "backend": [
        "backend.backend_project_init",
        "backend.crud_module_generator",
        "backend.backend_self_test",
    ],
    "frontend": [
        "frontend.frontend_project_init",
        "frontend.static_page_build",
        "frontend.frontend_self_test",
    ],
    "testing": [
        "testing.test_plan",
        "testing.test_driven_development",
        "testing.regression_test_suite",
    ],
    "security": [
        "security.full_security_audit",
        "security.rbac_overpermission_check",
        "security.security_acceptance_gate",
    ],
    "deployment": [
        "deployment_ops.docker_deploy",
        "deployment_ops.env_variables_config",
        "deployment_ops.rollback_plan",
    ],
    "launch_hardening": [
        "security.full_security_audit",
        "deployment_ops.docker_deploy",
        "testing.release_acceptance_test",
    ],
    "iteration": [
        "iteration.version_planning",
        "iteration.feedback_triage",
        "core.scope_controller",
    ],
}

P0_ROLE_RULES: list[tuple[re.Pattern[str], str, list[str]]] = [
    (
        re.compile(r"只读|cypher|租户|tenant|越权|acl|上传|隔离", re.I),
        "security_engineer",
        [
            "security.rbac_overpermission_check",
            "backend.file_upload_storage",
            "security.full_security_audit",
        ],
    ),
    (
        re.compile(r"ready|跨存储|chroma|原子|空洞|outbox|失败联调|断一端", re.I),
        "backend_engineer",
        [
            "backend.transaction_idempotency",
            "backend.complex_business_logic",
            "integration_debugging.systematic_debugging",
        ],
    ),
    (
        re.compile(r"tls|密钥|secret|compose|端口|nginx|回滚|部署|kms", re.I),
        "devops_engineer",
        [
            "deployment_ops.nginx_ssl_domain",
            "deployment_ops.env_variables_config",
            "deployment_ops.rollback_plan",
        ],
    ),
    (
        re.compile(r"空库|grounded|ui|前端|工作台|警示", re.I),
        "frontend_engineer",
        [
            "frontend.error_empty_loading_states",
            "frontend.static_page_build",
            "frontend.frontend_self_test",
        ],
    ),
    (
        re.compile(r"测试入口|pytest|回归套件", re.I),
        "qa_engineer",
        ["testing.test_driven_development", "testing.regression_test_suite"],
    ),
]


def find_pack_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "skills" / "00_core").is_dir():
            return candidate
    script_pack = Path(__file__).resolve().parents[4]
    if (script_pack / "skills" / "00_core").is_dir():
        return script_pack
    return start


def find_project_root(pack_root: Path, start: Path) -> Path:
    project = pack_root / "project"
    if project.is_dir():
        return project
    if (start / "ROADMAP.md").exists() or (start / "code").is_dir():
        return start
    return pack_root


def dir_has_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(p.is_file() for p in path.rglob("*"))


def strip_done_clauses(text: str) -> str:
    text = re.sub(r"（[^）]*已落地[^）]*）", "", text)
    text = re.sub(r"~~.*?~~", "", text)
    parts = re.split(r"[＋+；;]", text)
    remain = []
    for part in parts:
        if re.search(r"已落地|已完成|已通过|已确认", part) and not re.search(
            r"仍缺|未做|未过|未落地|待", part
        ):
            continue
        cleaned = re.sub(r"\*+", "", part).strip(" ：:。")
        if cleaned:
            remain.append(cleaned)
    preferred = [
        p for p in remain if re.search(r"仍缺|未做|未过|联调|演练|未落地|待验证|待", p)
    ]
    return next((p for p in (preferred or remain) if p), text)


def glob_exists(root: Path, pattern: str) -> list[str]:
    matches = [p for p in root.glob(pattern) if p.is_file() or (p.is_dir() and any(p.iterdir()))]
    rels: list[str] = []
    for path in matches[:12]:
        try:
            rels.append(str(path.relative_to(root)))
        except ValueError:
            rels.append(str(path))
    return rels


def detect_layout(project_root: Path) -> str:
    canonical_live = dir_has_files(project_root / "backend") or dir_has_files(
        project_root / "frontend"
    )
    has_code = dir_has_files(project_root / "code")
    if has_code and canonical_live:
        return "mixed"
    if has_code:
        return "code_monorepo"
    if canonical_live:
        return "canonical"
    return "unknown"


def load_skill_paths(pack_root: Path) -> dict[str, str]:
    matrix = pack_root / "skill_routing_matrix.json"
    if not matrix.is_file():
        return {}
    try:
        data = json.loads(matrix.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {item["id"]: item.get("path", "") for item in data if "id" in item}


def score_domains(project_root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for domain, globs in DOMAIN_GLOBS.items():
        hits: list[str] = []
        for pattern in globs:
            hits.extend(glob_exists(project_root, pattern))
        # unique preserve order
        seen: set[str] = set()
        unique = []
        for h in hits:
            if h not in seen:
                seen.add(h)
                unique.append(h)
        status = "present" if unique else "missing"
        out[domain] = {"status": status, "hits": unique[:8], "hit_count": len(unique)}
    return out


def first_incomplete_stage(domains: dict[str, dict[str, Any]]) -> str:
    for stage in STAGE_ORDER:
        if domains.get(stage, {}).get("status") == "missing":
            return stage
    if domains.get("deployment", {}).get("status") == "present":
        return "iteration"
    return "backend"


def parse_roadmap(roadmap: Path) -> dict[str, Any]:
    if not roadmap.is_file():
        return {"exists": False}
    text = roadmap.read_text(encoding="utf-8", errors="replace")

    next_actions: list[dict[str, Any]] = []
    in_next = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("### 下一执行顺序"):
            in_next = True
            continue
        if in_next:
            if line.startswith("## ") or line.startswith("### ") and "下一执行顺序" not in line:
                break
            m = re.match(r"^(\d+)\.\s+(.*)$", line)
            if not m:
                continue
            body = m.group(2).strip()
            done = body.startswith("~~") or "已完成" in body or "已通过" in body
            next_actions.append({"text": re.sub(r"~~", "", body).strip(), "done": done})

    p0: list[dict[str, str]] = []
    current_id = ""
    current_title = ""
    current_status = ""
    missing: list[str] = []
    in_still_missing = False

    def flush() -> None:
        if not current_id:
            return
        p0.append(
            {
                "id": current_id,
                "title": current_title,
                "status": current_status or "unknown",
                "still_missing": "；".join(missing)[:400],
            }
        )

    for raw in text.splitlines():
        heading = re.match(r"^### (P0-\d+)\s+(.*)$", raw.strip())
        if heading:
            flush()
            current_id, current_title = heading.group(1), heading.group(2).strip()
            current_status = ""
            missing = []
            in_still_missing = False
            continue
        if current_id and raw.startswith("### "):
            flush()
            current_id = ""
            in_still_missing = False
            continue
        if not current_id:
            continue
        st = re.search(r"\*\*状态[：:]\s*(.+?)\*\*", raw)
        if not st:
            st = re.search(r"\*\*状态[：:]\*\*\s*(.+)$", raw)
        if st:
            current_status = st.group(1).strip()
            in_still_missing = False
            continue
        if raw.strip().startswith("**仍缺"):
            in_still_missing = True
            rest = raw.split("：**", 1)
            if len(rest) == 2 and rest[1].strip():
                missing.append(rest[1].strip())
            continue
        if in_still_missing:
            if raw.startswith("**") or raw.startswith("##") or raw.startswith("###"):
                in_still_missing = False
            elif raw.strip().startswith("- ") or raw.strip():
                missing.append(raw.strip().lstrip("- ").strip())

    flush()

    remaining = [
        item
        for item in p0
        if "❌" in item["status"] or "⚠️" in item["status"] or "未达标" in item["status"]
    ]
    open_next = [a for a in next_actions if not a["done"]]

    return {
        "exists": True,
        "path": str(roadmap),
        "next_actions": next_actions[:8],
        "open_next_actions": open_next[:5],
        "p0": p0,
        "p0_remaining": remaining,
        "p0_remaining_ids": [x["id"] for x in remaining],
    }


def role_from_text(text: str, default_role: str, default_skills: list[str]) -> tuple[str, list[str]]:
    for pattern, role, skills in P0_ROLE_RULES:
        if pattern.search(text):
            return role, skills
    return default_role, default_skills


def recommend(domains: dict[str, dict[str, Any]], roadmap: dict[str, Any], layout: str) -> dict[str, Any]:
    has_code = domains["backend"]["status"] != "missing" or domains["api"]["status"] != "missing"
    p0_remaining = roadmap.get("p0_remaining") or []
    open_next = roadmap.get("open_next_actions") or []

    if roadmap.get("exists") and has_code and (p0_remaining or open_next):
        raw_slice = (
            open_next[0]["text"]
            if open_next
            else p0_remaining[0].get("still_missing") or p0_remaining[0]["title"]
        )
        slice_text = strip_done_clauses(raw_slice)
        role, skills = role_from_text(slice_text, "backend_engineer", STAGE_TO_SKILLS["backend"])
        mode = "strict"
        return {
            "stage": "launch_hardening",
            "role": role,
            "mode": mode,
            "recommended_skills": skills[:3],
            "next_slice": slice_text[:240],
            "why": "ROADMAP P0/下一刀仍未关闭；以企业验收为准，不退回重写需求。",
        }

    stage = first_incomplete_stage(domains)
    if has_code and stage in {"requirements", "product_design", "architecture", "database"}:
        if domains["testing"]["status"] == "missing":
            stage = "testing"
        elif domains["security"]["status"] == "missing":
            stage = "security"
        elif domains["deployment"]["status"] == "missing":
            stage = "deployment"
        else:
            stage = "launch_hardening"

    role = STAGE_TO_ROLE[stage]
    skills = STAGE_TO_SKILLS[stage]
    mode = "strict" if stage in {"security", "deployment", "database", "launch_hardening"} else "standard"
    missing = [s for s in STAGE_ORDER if domains[s]["status"] == "missing"]
    next_slice = f"补齐 {stage} 阶段最早缺口" if missing else "维护与迭代"
    return {
        "stage": stage,
        "role": role,
        "mode": mode,
        "recommended_skills": skills[:3],
        "next_slice": next_slice,
        "why": f"按产物扫描，最早缺口阶段={stage}；layout={layout}。",
    }


def blockers(project_root: Path, domains: dict[str, dict[str, Any]], rec: dict[str, Any]) -> list[str]:
    items: list[str] = []
    env = None
    for candidate in (
        project_root / "code" / "python" / ".env",
        project_root / ".env",
        project_root / "backend" / ".env",
    ):
        if candidate.is_file():
            env = candidate
            break
    if rec["role"] in {"devops_engineer", "qa_engineer"} and env is None:
        example = project_root / "code" / "python" / ".env.example"
        if example.is_file():
            items.append(f"未找到 .env（仅有 example：{example.relative_to(project_root)}），真实联调会被阻塞。")
    if not (project_root / "code" / "python" / "scripts" / "run_unit_tests.sh").is_file() and domains["backend"]["status"] != "missing":
        if not list((project_root / "tests").glob("**/*")) if (project_root / "tests").exists() else True:
            items.append("未找到固定测试入口。")
    if rec["stage"] == "launch_hardening":
        items.append("P0 未清零前不得宣称可售/可上线。")
    return items


def main() -> int:
    start = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    pack_root = find_pack_root(start)
    project_root = find_project_root(pack_root, start)
    layout = detect_layout(project_root)
    domains = score_domains(project_root)
    roadmap = parse_roadmap(project_root / "ROADMAP.md")
    rec = recommend(domains, roadmap, layout)
    skill_index = load_skill_paths(pack_root)
    rec["skill_paths"] = [skill_index[s] for s in rec["recommended_skills"] if s in skill_index]
    empty_canonical = [
        name
        for name in ("backend", "frontend", "sql", "tests", "scripts")
        if (project_root / name).is_dir() and not dir_has_files(project_root / name)
    ]
    report = {
        "pack_root": str(pack_root),
        "project_root": str(project_root),
        "layout": layout,
        "primary_code_root": str(project_root / "code" / "python")
        if layout == "code_monorepo"
        else str(project_root / "backend"),
        "empty_canonical_dirs": empty_canonical,
        "domains": domains,
        "roadmap": {
            "exists": roadmap.get("exists"),
            "open_next_actions": roadmap.get("open_next_actions", []),
            "p0_remaining_ids": roadmap.get("p0_remaining_ids", []),
            "p0_remaining": roadmap.get("p0_remaining", []),
        },
        **rec,
        "blockers": blockers(project_root, domains, rec),
        "do_not": [
            "不要把业务代码写入 skills/、templates/、examples/",
            "若 layout=code_monorepo，不要空建 project/backend 或 project/frontend 来对齐规范",
            "不要在无测试证据时把 ROADMAP 标成已验收",
        ],
        "skill_files_to_read": {
            "roles": ".cursor/skills/fullstack-dev-orchestrator/roles.md",
            "signals": ".cursor/skills/fullstack-dev-orchestrator/progress-signals.md",
            "hard_gates": "HARD_GATES.md",
        },
    }

    print("# Fullstack progress assessment")
    print()
    print(f"- pack_root: `{report['pack_root']}`")
    print(f"- project_root: `{report['project_root']}`")
    print(f"- layout: `{layout}`")
    print(f"- stage: `{rec['stage']}`")
    print(f"- role: `{rec['role']}`")
    print(f"- mode: `{rec['mode']}`")
    print(f"- next_slice: {rec['next_slice']}")
    print(f"- why: {rec['why']}")
    print(f"- skills: {', '.join(rec['recommended_skills'])}")
    if rec.get("skill_paths"):
        print("- skill_paths:")
        for path in rec["skill_paths"]:
            print(f"  - `{path}`")
    if empty_canonical:
        print(f"- empty_canonical_dirs: {', '.join(empty_canonical)}（不要往这些空目录填业务代码，用 `code/`）")
    if report["blockers"]:
        print("- blockers:")
        for b in report["blockers"]:
            print(f"  - {b}")
    print()
    print("## Domain hits")
    for name in STAGE_ORDER:
        d = domains[name]
        print(f"- {name}: {d['status']} ({d['hit_count']})")
    if roadmap.get("open_next_actions"):
        print()
        print("## Open ROADMAP next actions")
        for item in roadmap["open_next_actions"]:
            print(f"- {item['text']}")
    print()
    print("## JSON")
    print("```json")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
