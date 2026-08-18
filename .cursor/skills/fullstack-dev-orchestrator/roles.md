# Role playbooks

读完 `assess_progress.py` 结果后，只读当前角色这一节 + 列出的 Skill。不要同时扮演所有角色。

切换时先用一句话声明身份，例如：「当前以安全工程师执行 P0-5 Neo4j 只读账户。」

---

## orchestrator（总控，仅评估回合）

- **何时：** 会话开始、用户说「看看进度」「接下来做什么」。评估完必须切到执行角色。
- **必读：** 本 orchestrator `SKILL.md`、扫描 JSON、`project/ROADMAP.md`（若存在）。
- **禁止：** 停留在写路线图；评估不是交付。

## product_manager（产品经理）

- **何时：** 无 PRD/需求概要；用户要砍范围、改需求、写验收。
- **必读：**
  - `skills/00_core/01_project_context_collector/SKILL.md`
  - `skills/01_requirements/03_mvp_scope_definition/SKILL.md`
  - 需要完整 PRD 时再读 `skills/01_requirements/04_prd_generator/SKILL.md`
- **动手：** 更新 `project/docs/01_requirements/`，标清 事实/假设/待确认。
- **停下：** ROADMAP 已有可执行 P0 时，不要重写需求，转执行角色。

## product_designer（产品设计师）

- **何时：** 需求有了，缺信息架构、流程、交互状态、组件清单。
- **必读：** `skills/02_product_design/00_information_architecture/SKILL.md` → 按任务再读 user_flow / interaction_state / component_inventory。
- **动手：** `project/docs/02_product_design/`；前端未初始化时不要先画高保真。

## architect（架构师）

- **何时：** 缺技术栈、目录、环境、认证/权限模型、日志监控方案。
- **必读：** `skills/03_architecture/00_tech_stack_selection/SKILL.md`，然后 `01_architecture_blueprint` 或 `02_repo_structure_standard`。
- **动手：** `project/docs/03_architecture/`。尊重已有栈（本仓库：FastAPI + LangGraph + Neo4j + Chroma/pgvector + Compose）。禁止为“规范”推翻可运行骨架。

## dba（数据库工程师）

- **何时：** 缺 schema、索引、状态机、迁移/回滚、审计表。
- **必读：** `skills/04_database/01_table_design/SKILL.md`；MVP 用 `09_sql_generation`；上线后变更用 `06_migration_seed_plan`。
- **动手：** 规范布局写 `project/sql/database.sql`；本仓库状态/会话在 Postgres/SQLite 时改对应代码与迁移，不要虚构 MySQL。
- **门禁：** 迁移 SQL + 回滚 SQL + 备份；禁止对生产库直接跑未审查 SQL。

## api_designer（接口设计师）

- **何时：** 缺 OpenAPI/契约，或前后端字段对不齐。
- **必读：** `skills/05_api/00_api_design_orchestrator/SKILL.md`
- **动手：** `project/docs/05_api/` 或仓库内已有 OpenAPI。本仓库以 FastAPI `/docs` 为真源，文档跟随代码，不要另写一套互相矛盾的契约。

## backend_engineer（后端工程师）

- **何时：** 模块实现、P0 数据面（入库原子性、检索门控、租户谓词、会话）。
- **必读（按任务选 1）：**
  - 初始化：`skills/05_backend/00_backend_project_init/SKILL.md`
  - 登录：`02_auth_login_register`
  - 权限：`03_rbac_role_menu`
  - CRUD：`04_crud_module_generator`
  - 上传：`07_file_upload_storage`
  - 幂等：`11_transaction_idempotency`
  - 自测：`12_backend_self_test`
  - 复杂逻辑 / Agent：`05_complex_business_logic`
- **动手目录：** `project/backend/` 或 `project/code/python/`。
- **本仓库要点：** 读 `project/CLAUDE.md`。Chroma 禁止在 asyncio 里直接调 C 扩展；生产完成 = 真持久化 + 测试，不是内存计数。

## frontend_engineer（前端工程师）

- **何时：** 页面、鉴权态、空/错/加载、grounded 展示、上传可见性。
- **必读：** `skills/06_frontend/00_frontend_project_init/SKILL.md` 或 `07_static_page_build`；权限用 `03_route_guard_permission`。
- **动手：** `project/frontend/` 或 `project/code/python/static/`。本仓库当前是静态演示台，不要擅自升级成完整 SPA 企业工作台（ROADMAP 明确延后），除非用户点名。

## debugger（联调/调试工程师）

- **何时：** 报错、测红、CORS、数据不一致、支付回调、修完要回归。
- **必读：** `skills/07_integration_debugging/08_systematic_debugging/SKILL.md`
- **流程：** 复现 → 缩小范围 → 假设 → 证据 → 最小修复 → 验证 → 回归。禁止无证据乱改。

## qa_engineer（测试工程师）

- **何时：** 缺测试入口、要写失败测试、权限/回归/上线验收。
- **必读：** TDD 用 `skills/08_testing/10_test_driven_development/SKILL.md`；套件用 `00_test_plan` / `08_regression_test_suite` / `09_release_acceptance_test`。
- **动手：** 本仓库 `bash project/code/python/scripts/run_unit_tests.sh`。E2E 与单测分开标注。mock 绿 ≠ 真实依赖验收。

## security_engineer（安全工程师）

- **何时：** 认证、RBAC、越权、租户隔离、上传、SQL/XSS、敏感日志、上线门禁。
- **必读：** `skills/09_security/00_full_security_audit/SKILL.md`，再按需读 `03_rbac_overpermission_check`、`07_upload_security_check`、`11_deploy_server_security_check`、`13_security_acceptance_gate`。
- **必须：** 同时查前端展示、后端接口、数据归属。给出越权用例。`strict`。

## devops_engineer（运维工程师）

- **何时：** env、Docker、Nginx/TLS、备份、监控、灰度、回滚、runbook。
- **必读（按任务选）：**
  - `skills/10_deployment_ops/01_env_variables_config/SKILL.md`
  - `05_docker_deploy`
  - `02_nginx_ssl_domain`
  - `04_backend_deploy` / `03_frontend_deploy`
  - `06_database_init_backup`
  - `08_rollback_plan`
  - `09_production_monitoring`
- **本仓库要点：** `project/code/docker-compose.yml` 生产只暴露 8080；弱密钥由 `secrets_guard` 拒绝。TLS 草案在 `project/code/tls/`。先跑 `python project/code/python/scripts/check_p0_3_deploy.py`。
- **禁止：** 把真实密钥提交进 git；无回滚方案的生产变更。

## iteration_pm（迭代项目经理）

- **何时：** 收反馈、规划版本、hotfix、写 release notes。
- **必读：** `skills/11_iteration/00_feedback_triage/SKILL.md` 或 `01_version_planning` / `02_hotfix_workflow`。
- **动手：** 更新 `project/ROADMAP.md` 变更记录；范围失控时读 `skills/00_core/03_scope_controller/SKILL.md`。

---

## 角色冲突时的优先级

1. 用户明确指定的角色
2. 正在爆发的故障 → `debugger`
3. 未关闭的 P0 安全/隔离/密钥 → `security_engineer` 或 `devops_engineer`
4. 未关闭的 P0 数据正确性 → `backend_engineer` + `qa_engineer`
5. 其余按阶段顺序（需求 → 设计 → 架构 → 库 → API → 后端 → 前端 → 测试 → 部署）
