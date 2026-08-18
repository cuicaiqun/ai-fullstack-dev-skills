# Progress signals

用仓库里的真实文件判断阶段。扫描脚本已覆盖下列路径；人工抽查时用同一套信号。

## 1. Find roots

| 根 | 判据 |
|---|---|
| pack root | 存在 `skills/00_core/`，通常还有 `00_MASTER_PROMPT.md` |
| project root | `pack/project/`；若工作区就是业务仓且无上层 pack，则当前仓即 project |

业务代码不要到 `skills/05_backend/` 里找。

## 2. Layouts

**canonical（规范）**

```text
project/backend/   project/frontend/   project/docs/
project/sql/database.sql   project/tests/   project/scripts/
```

**code_monorepo（本仓库现行）**

```text
project/code/python/          # FastAPI + agents + tests
project/code/python/static/   # 演示 UI
project/code/docker-compose.yml
project/code/tls/
project/docs/   project/ROADMAP.md   project/CLAUDE.md
```

`layout` 为 `code_monorepo` 或 `mixed` 时：所有写入跟现行树走。空的 `project/backend/`、`project/frontend/` 只是占位，不要往里面填业务代码。

## 3. Artifact → stage

按顺序查找**最早缺口**。已有 ROADMAP 且 P0 未清零时，阶段锁定为 `launch_hardening`，不要回到 `requirements`。

| 顺序 | 阶段 `stage` | 视为已有（任一命中） | 常见缺口 |
|---:|---|---|---|
| 1 | `requirements` | `docs/01_requirements/`、`*PRD*`、`requirements_brief.md` | 无用户、无 MVP、无验收 |
| 2 | `product_design` | `docs/02_product_design/`、`page_structure.md` | 无页面树/流程 |
| 3 | `architecture` | `docs/03_architecture/`、`CLAUDE.md`、技术选型文档 | 无栈无目录 |
| 4 | `database` | `sql/database.sql`、`docs/04_database/`、模型/迁移 | 无表无回滚 |
| 5 | `api` | `docs/05_api/`、openapi、FastAPI `api/` 路由 | 无契约 |
| 6 | `backend` | `backend/`、`code/python/api/` | 模块空心 |
| 7 | `frontend` | `frontend/`、`**/static/` | 仅占位 UI |
| 8 | `testing` | `tests/`、`docs/07_testing/`、`run_unit_tests.sh` | 无固定入口 |
| 9 | `security` | auth/acl、secrets_guard、安全文档 | 越权未测 |
| 10 | `deployment` | compose/Dockerfile/tls、`docs/09_deployment/` | 无备份无回滚 |
| 11 | `launch_hardening` | 有 ROADMAP P0/P1 | 企业验收未过 |
| 12 | `iteration` | 已有生产叙述或用户反馈 | 范围膨胀 |

## 4. ROADMAP overlay（本仓库）

读 `project/ROADMAP.md`：

1. 「下一执行顺序」里**未删除线**的条目 = `next_slice` 候选。
2. `### P0-x` 下 `**状态：**` 含 ❌ 或 ⚠️，且「仍缺」非空 = 未关闭。
3. 图例：✅ 有实现+证据；⚠️ 薄切片未达企业验收；❌ 不能对客户宣称完成。
4. 状态必须以代码路径 + 测试为准，禁止只改 ROADMAP 勾选。

P0 关键词 → 角色：

| 关键词 | role_id |
|---|---|
| 只读账户 / Cypher / 租户 / 越权 / ACL / 上传 | `security_engineer` 或 `backend_engineer` |
| TLS / 密钥 / compose / 端口 / 回滚演练 | `devops_engineer` |
| ready 过滤 / 断存储 / 原子性 | `backend_engineer` |
| pytest / 测试入口 / E2E | `qa_engineer` |
| 空库引导 / grounded / UI | `frontend_engineer` |

## 5. Completeness scoring (script)

每个域：`missing` / `partial` / `present`。

- `present`：关键文件存在，且 ROADMAP 该项为 ✅（若无 ROADMAP，仅看文件）。
- `partial`：有代码或文档，但 ROADMAP 为 ⚠️/❌，或缺测试脚本。
- `missing`：域内 0 个命中。

`recommended_skills` 只返回 **3 个以内** route_id，对应 `skill_routing_matrix.json`。

## 6. Manual spot-check (if script fails)

1. `ls project/` 与 `ls project/code 2>/dev/null`
2. 读 `project/ROADMAP.md` 前 80 行 + 「下一执行顺序」
3. 读 `project/docs/README.md`、`project/CLAUDE.md`
4. 有测试则看 `project/code/python/scripts/run_unit_tests.sh` 是否存在

然后按 `SKILL.md` 选角色，禁止空等用户补充“当前阶段”。
