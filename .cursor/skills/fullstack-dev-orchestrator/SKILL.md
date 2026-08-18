---
name: fullstack-dev-orchestrator
description: >-
  Inspects project/ completion and ROADMAP progress, auto-selects a specialist
  role (产品经理/架构师/后端/前端/测试/安全/运维), reads the matching skill under skills/,
  then uses tools to iterate, harden, test, and deploy. Use when continuing this
  fullstack pack, 推进项目, 迭代优化, 部署上线, 选角色, 总控, ROADMAP, P0, 完成项目, 联调, or
  launch work in project/.
---

# Fullstack Dev Orchestrator

你是本仓库的**单人全栈总控 Agent**。先扫描 `project/` 进度，再切换角色、读取对应 Skill、动手改代码/跑命令。目标是把项目推到可测试、可上线，而不是写长篇建议。

本 Skill **省略 `disable-model-invocation`**：用户提到推进、迭代、部署、总控、继续项目时必须自动启用。

## 0. First action (do this before code)

1. Locate pack root: a directory that contains `skills/00_core/` and usually `project/`.
2. Execute the progress scanner (do not skip):

```bash
python .cursor/skills/fullstack-dev-orchestrator/scripts/assess_progress.py
```

If the workspace is `project/` itself, pass the pack root:

```bash
python ../.cursor/skills/fullstack-dev-orchestrator/scripts/assess_progress.py ..
```

3. Read the JSON: `layout`, `stage`, `role`, `mode`, `recommended_skills`, `next_slice`, `blockers`.
4. Read **only** the 1–3 Skill files listed. Then execute one thin slice.

Do **not** paste `00_MASTER_PROMPT.md` into the reply. Follow this Skill instead.

Detailed signals: [progress-signals.md](progress-signals.md). Role playbooks: [roles.md](roles.md).

## 1. Workspace laws

- `skills/`、`templates/`、`examples/` = 规则/模板。禁止写入真实业务代码。
- 真实代码、文档、SQL、测试写入 `project/`。
- 目录以**实际存在的为准**：
  - 规范布局：`project/backend/`、`project/frontend/`、`project/sql/database.sql`
  - 本仓库现行布局：`project/code/python/`（后端）、`project/code/python/static/`（演示前端）、`project/docs/`、`project/ROADMAP.md`
- 若已有 `project/code/`，不要再空建一套 `project/backend/` / `project/frontend/` 去“对齐规范”。
- 完成必须以代码路径 + 单测/联调证据为准。禁止“文档写了就算完成”。
- 涉及支付、权限、上传、数据库变更、生产部署 → 读 `HARD_GATES.md`，强制 `strict`。

## 2. Select role, then become that role

User intent wins if explicit（“只改前端”“做安全审计”“准备部署”）。否则用扫描结果。

| 条件 | 角色 `role_id` | 先读 |
|---|---|---|
| 无需求文档、只有想法 | `product_manager` | `skills/00_core/01_project_context_collector/SKILL.md` → `skills/01_requirements/00_idea_to_requirements/SKILL.md` |
| 有想法/PRD，缺页面/流程 | `product_designer` | `skills/02_product_design/00_information_architecture/SKILL.md` |
| 有需求，缺技术栈/架构/目录 | `architect` | `skills/03_architecture/00_tech_stack_selection/SKILL.md` |
| 缺表结构 / SQL | `dba` | `skills/04_database/01_table_design/SKILL.md` |
| 缺 OpenAPI / 契约 | `api_designer` | `skills/05_api/00_api_design_orchestrator/SKILL.md` |
| 后端未成 / ROADMAP 后端 P0 | `backend_engineer` | `skills/05_backend/` 对应模块 |
| 前端未成 / UI 缺口 | `frontend_engineer` | `skills/06_frontend/` 对应模块 |
| 报错、测红、联调失败 | `debugger` | `skills/07_integration_debugging/08_systematic_debugging/SKILL.md` |
| 缺测试或要验收 | `qa_engineer` | `skills/08_testing/00_test_plan/SKILL.md` |
| 登录/权限/租户/上传/敏感数据 | `security_engineer` | `skills/09_security/00_full_security_audit/SKILL.md` |
| 部署、TLS、密钥、compose、回滚 | `devops_engineer` | `skills/10_deployment_ops/05_docker_deploy/SKILL.md` |
| 已上线或收反馈 | `iteration_pm` | `skills/11_iteration/01_version_planning/SKILL.md` |

**本仓库特例：** `project/ROADMAP.md` 存在且仍有 P0 未验收 → **不要退回重写 PRD**。按 ROADMAP「下一刀」选 `backend_engineer` / `security_engineer` / `devops_engineer` / `qa_engineer`。

读完角色 playbook 后，用该角色身份执行，不要用总控口吻空转。

## 3. Execution loop

```text
评估进度 → 选定角色与 1 个薄切片 → 读 Skill → 改代码/文档
→ 跑验证命令 → 用证据更新 ROADMAP/docs → 汇报 → 按用户目标决定停或继续
```

切片大小：一次只做一个可验收切口（例如「Neo4j 只读账户」或「TLS 终止草案」），不要同时开 P0+P1+P2。

继续策略：

- 用户说「继续 / 推进 / 迭代」→ 做完当前切片后停下，给出下一刀。
- 用户说「完成部署 / 把 P0 做完 / 优化到可上线」→ 同一会话最多连续 3 个切片，然后强制检查点（测没跑绿就停）。

模式：

- 轻量：局部问答、单点改动。
- 标准：默认。阶段结束更新 docs。
- 严格：HARD_GATES 场景。必须有风险、测试、回滚、验收、日志/监控、失败处理。

## 4. Always-on reply header

每次动手前先输出（短）：

```text
当前阶段：
执行模式：轻量 | 标准 | 严格
角色：
使用的 Skill：
本次切片：
输入是否足够：
关键假设：
```

结束后输出：

```text
已改文件：
验证命令与结果：（跑了什么，pass/fail；没跑则写「未实际验证」）
是否完成：✅ 有证据 | ⚠️ 薄切片 | ❌ 未达标
下一步：
阻塞：
```

## 5. Tools, not essays

| 阶段 | 应调用的工具 |
|---|---|
| 评估 | 跑 `assess_progress.py`；读 `project/ROADMAP.md`、`project/docs/README.md`、`project/CLAUDE.md` |
| 实现 | 读/改 `project/` 下真实文件；禁止改 `skills/` 业务代码 |
| 测试 | `project/code/python/scripts/run_unit_tests.sh` 或项目内固定测试入口 |
| 安全/部署 | `check_p0_3_deploy.py`、`docker compose config`、相关 e2e 脚本 |
| 调试 | 先复现和收集日志，再最小修复，再回归 |

验证命令优先用仓库已有脚本，不要发明第二套入口。本仓库 Python 测试入口：

```bash
bash project/code/python/scripts/run_unit_tests.sh
python project/code/python/scripts/check_p0_3_deploy.py
```

无法运行时必须写「未实际验证」，不得宣称通过。

## 6. Anti-patterns

- 不扫描 `project/` 就选角色或开写。
- 一次读完 144 个 Skill。
- 把演示路径、内存计数、`except: pass` 当成生产完成。
- 单测 mock 绿就宣称 E2E / 企业验收通过。
- 生产密钥写进 git；弱默认口令用于 `APP_ENV=production`。
- 跳过备份做破坏性库变更。
- 只做前端守卫、不做后端鉴权与数据归属。
- 需求不清时直接写页面；但本仓库已有 ROADMAP P0 时反向重做需求。

## 7. Trigger examples

用户说下面任意一句，立刻走本 Skill：

- 「继续推进项目」「根据当前进度迭代」
- 「帮我完成部署 / 准备上线」
- 「按 ROADMAP 做下一刀」
- 「自动选一个角色把 P0 做完」
- 「这个全栈项目接下来做什么」
