# Skill 路由矩阵


## 全局项目目录硬规则

- `skills/`、`templates/`、`examples/` 是技能包自身目录，只能放规则、模板和示例。
- 真实业务后端代码必须写入 `project/backend/`。
- 真实业务前端代码必须写入 `project/frontend/`。
- 业务项目文档写入 `project/docs/`，SQL 写入 `project/sql/database.sql`。
- 禁止在技能包根目录直接创建 `backend/` 或 `frontend/`。


生成日期：2026-07-01

本文件用于让 AI 在执行任务前快速判断：该用哪个 Skill、前置材料是什么、风险等级如何、必须禁止什么、下一步接哪个 Skill。

完整机器可读版本见 `skill_routing_matrix.json`。

| stage_order | stage | route_id | Skill | 风险 | 模式 | 路径 |
|---:|---|---|---|---|---|---|
| 0 | core | `core.change_request_manager` | 需求变更管控 | high | strict | `skills/00_core/04_change_request_manager/SKILL.md` |
| 0 | core | `core.document_deliverable_manager` | 文档交付管理 | high | strict | `skills/00_core/05_document_deliverable_manager/SKILL.md` |
| 0 | core | `core.project_context_collector` | 项目上下文收集 | high | strict | `skills/00_core/01_project_context_collector/SKILL.md` |
| 0 | core | `core.project_orchestrator` | 项目总控官 | high | strict | `skills/00_core/00_project_orchestrator/SKILL.md` |
| 0 | core | `core.scope_controller` | MVP 范围控制 | high | strict | `skills/00_core/03_scope_controller/SKILL.md` |
| 0 | core | `core.stage_gate_reviewer` | 阶段门禁评审 | high | strict | `skills/00_core/02_stage_gate_reviewer/SKILL.md` |
| 1 | requirements | `requirements.acceptance_criteria_builder` | 验收标准生成 | high | strict | `skills/01_requirements/08_acceptance_criteria_builder/SKILL.md` |
| 1 | requirements | `requirements.business_process_mapping` | 业务流程梳理 | high | strict | `skills/01_requirements/02_business_process_mapping/SKILL.md` |
| 1 | requirements | `requirements.business_rule_spec` | 业务规则定义 | high | strict | `skills/01_requirements/06_business_rule_spec/SKILL.md` |
| 1 | requirements | `requirements.exception_scenario_mining` | 异常场景挖掘 | high | strict | `skills/01_requirements/07_exception_scenario_mining/SKILL.md` |
| 1 | requirements | `requirements.idea_to_requirements` | 想法转需求 | high | strict | `skills/01_requirements/00_idea_to_requirements/SKILL.md` |
| 1 | requirements | `requirements.mvp_scope_definition` | MVP 范围定义 | high | strict | `skills/01_requirements/03_mvp_scope_definition/SKILL.md` |
| 1 | requirements | `requirements.page_function_spec` | 页面功能说明 | high | strict | `skills/01_requirements/05_page_function_spec/SKILL.md` |
| 1 | requirements | `requirements.prd_generator` | PRD 生成 | high | strict | `skills/01_requirements/04_prd_generator/SKILL.md` |
| 1 | requirements | `requirements.requirement_change_order` | 需求变更单 | high | strict | `skills/01_requirements/10_requirement_change_order/SKILL.md` |
| 1 | requirements | `requirements.requirements_review` | 需求评审 | high | strict | `skills/01_requirements/09_requirements_review/SKILL.md` |
| 1 | requirements | `requirements.user_role_permission_analysis` | 用户角色与权限分析 | high | strict | `skills/01_requirements/01_user_role_permission_analysis/SKILL.md` |
| 2 | product_design | `product_design.component_inventory` | 组件清单 | high | strict | `skills/02_product_design/07_component_inventory/SKILL.md` |
| 2 | product_design | `product_design.design_review` | 设计评审 | high | strict | `skills/02_product_design/09_design_review/SKILL.md` |
| 2 | product_design | `product_design.form_design_rules` | 表单设计规则 | high | strict | `skills/02_product_design/04_form_design_rules/SKILL.md` |
| 2 | product_design | `product_design.information_architecture` | 信息架构设计 | high | strict | `skills/02_product_design/00_information_architecture/SKILL.md` |
| 2 | product_design | `product_design.interaction_state_spec` | 交互状态设计 | high | strict | `skills/02_product_design/03_interaction_state_spec/SKILL.md` |
| 2 | product_design | `product_design.list_filter_pagination_design` | 列表筛选分页设计 | high | strict | `skills/02_product_design/05_list_filter_pagination_design/SKILL.md` |
| 2 | product_design | `product_design.microcopy_prompt_text` | 提示文案设计 | high | strict | `skills/02_product_design/08_microcopy_prompt_text/SKILL.md` |
| 2 | product_design | `product_design.ui_style_guide` | UI 风格规范 | high | strict | `skills/02_product_design/06_ui_style_guide/SKILL.md` |
| 2 | product_design | `product_design.user_flow_design` | 用户流程设计 | high | strict | `skills/02_product_design/01_user_flow_design/SKILL.md` |
| 2 | product_design | `product_design.wireframe_spec` | 低保真原型说明 | high | strict | `skills/02_product_design/02_wireframe_spec/SKILL.md` |
| 3 | architecture | `architecture.api_standard` | 接口规范 | high | strict | `skills/03_architecture/06_api_standard/SKILL.md` |
| 3 | architecture | `architecture.architecture_blueprint` | 整体架构方案 | high | strict | `skills/03_architecture/01_architecture_blueprint/SKILL.md` |
| 3 | architecture | `architecture.auth_architecture` | 认证架构 | high | strict | `skills/03_architecture/04_auth_architecture/SKILL.md` |
| 3 | architecture | `architecture.cache_strategy` | 缓存策略 | high | strict | `skills/03_architecture/09_cache_strategy/SKILL.md` |
| 3 | architecture | `architecture.environment_strategy` | 环境规划 | high | strict | `skills/03_architecture/03_environment_strategy/SKILL.md` |
| 3 | architecture | `architecture.error_handling_standard` | 异常处理规范 | high | strict | `skills/03_architecture/07_error_handling_standard/SKILL.md` |
| 3 | architecture | `architecture.logging_monitoring_plan` | 日志与监控方案 | high | strict | `skills/03_architecture/08_logging_monitoring_plan/SKILL.md` |
| 3 | architecture | `architecture.permission_model` | 权限模型 | high | strict | `skills/03_architecture/05_permission_model/SKILL.md` |
| 3 | architecture | `architecture.repo_structure_standard` | 项目目录结构规范 | high | strict | `skills/03_architecture/02_repo_structure_standard/SKILL.md` |
| 3 | architecture | `architecture.security_architecture` | 安全架构方案 | high | strict | `skills/03_architecture/11_security_architecture/SKILL.md` |
| 3 | architecture | `architecture.tech_stack_selection` | 技术栈选型 | high | strict | `skills/03_architecture/00_tech_stack_selection/SKILL.md` |
| 3 | architecture | `architecture.frontend_ui_library_selection` | 前端 UI 组件库选型 | high | strict | `skills/03_architecture/12_frontend_ui_library_selection/SKILL.md` |
| 3 | architecture | `architecture.third_party_service_plan` | 第三方服务方案 | high | strict | `skills/03_architecture/10_third_party_service_plan/SKILL.md` |
| 4 | database | `database.audit_log_table_design` | 审计日志表设计 | high | strict | `skills/04_database/07_audit_log_table_design/SKILL.md` |
| 4 | database | `database.backup_recovery_design` | 备份与恢复设计 | high | strict | `skills/04_database/08_backup_recovery_design/SKILL.md` |
| 4 | database | `database.data_permission_scope` | 数据权限字段设计 | high | strict | `skills/04_database/05_data_permission_scope/SKILL.md` |
| 4 | database | `database.entity_modeling` | 业务实体建模 | high | strict | `skills/04_database/00_entity_modeling/SKILL.md` |
| 4 | database | `database.index_design` | 索引设计 | high | strict | `skills/04_database/03_index_design/SKILL.md` |
| 4 | database | `database.migration_seed_plan` | 迁移与初始化数据 | high | strict | `skills/04_database/06_migration_seed_plan/SKILL.md` |
| 4 | database | `database.relationship_design` | 表关系设计 | high | strict | `skills/04_database/02_relationship_design/SKILL.md` |
| 4 | database | `database.sql_generation` | 单 SQL 生成器 | high | strict | `skills/04_database/09_sql_generation/SKILL.md` |
| 4 | database | `database.status_enum_design` | 状态枚举设计 | high | strict | `skills/04_database/04_status_enum_design/SKILL.md` |
| 4 | database | `database.table_design` | 数据表设计 | high | strict | `skills/04_database/01_table_design/SKILL.md` |
| 5 | api | `api.api_design_orchestrator` | 接口设计总控 | high | strict | `skills/05_api/00_api_design_orchestrator/SKILL.md` |
| 5 | api | `api.api_mock_validation` | 接口 Mock 与校验 | high | strict | `skills/05_api/03_api_mock_validation/SKILL.md` |
| 5 | api | `api.endpoint_contract_design` | 接口契约设计 | high | strict | `skills/05_api/02_endpoint_contract_design/SKILL.md` |
| 5 | api | `api.openapi_spec_generator` | OpenAPI 规范生成 | high | strict | `skills/05_api/01_openapi_spec_generator/SKILL.md` |
| 6 | backend | `backend.auth_login_register` | 登录注册模块 | high | strict | `skills/05_backend/02_auth_login_register/SKILL.md` |
| 6 | backend | `backend.backend_project_init` | 后端项目初始化 | high | strict | `skills/05_backend/00_backend_project_init/SKILL.md` |
| 6 | backend | `backend.backend_self_test` | 后端自测 | high | strict | `skills/05_backend/12_backend_self_test/SKILL.md` |
| 6 | backend | `backend.callback_webhook_handler` | 回调与 Webhook 处理 | high | strict | `skills/05_backend/08_callback_webhook_handler/SKILL.md` |
| 6 | backend | `backend.complex_business_logic` | 复杂业务逻辑 | high | strict | `skills/05_backend/05_complex_business_logic/SKILL.md` |
| 6 | backend | `backend.crud_module_generator` | 业务 CRUD 模块 | high | strict | `skills/05_backend/04_crud_module_generator/SKILL.md` |
| 6 | backend | `backend.file_upload_storage` | 文件上传与存储 | high | strict | `skills/05_backend/07_file_upload_storage/SKILL.md` |
| 6 | backend | `backend.order_payment_flow` | 订单支付流程 | high | strict | `skills/05_backend/06_order_payment_flow/SKILL.md` |
| 6 | backend | `backend.rbac_role_menu` | RBAC 角色权限菜单 | high | strict | `skills/05_backend/03_rbac_role_menu/SKILL.md` |
| 6 | backend | `backend.redis_cache_rate_limit` | Redis 缓存与限流 | high | strict | `skills/05_backend/10_redis_cache_rate_limit/SKILL.md` |
| 6 | backend | `backend.scheduler_job` | 定时任务 | high | strict | `skills/05_backend/09_scheduler_job/SKILL.md` |
| 6 | backend | `backend.transaction_idempotency` | 事务与幂等 | high | strict | `skills/05_backend/11_transaction_idempotency/SKILL.md` |
| 6 | backend | `backend.unified_response_exception` | 统一返回体与异常处理 | high | strict | `skills/05_backend/01_unified_response_exception/SKILL.md` |
| 7 | frontend | `frontend.api_client_wrapper` | 接口请求封装 | high | strict | `skills/06_frontend/05_api_client_wrapper/SKILL.md` |
| 7 | frontend | `frontend.base_components` | 基础组件封装 | high | strict | `skills/06_frontend/06_base_components/SKILL.md` |
| 7 | frontend | `frontend.error_empty_loading_states` | 空/加载/错误状态处理 | high | strict | `skills/06_frontend/10_error_empty_loading_states/SKILL.md` |
| 7 | frontend | `frontend.form_validation_submit` | 表单校验与提交 | high | strict | `skills/06_frontend/08_form_validation_submit/SKILL.md` |
| 7 | frontend | `frontend.frontend_project_init` | 前端项目初始化 | high | strict | `skills/06_frontend/00_frontend_project_init/SKILL.md` |
| 7 | frontend | `frontend.frontend_project_scaffold` | 前端项目初始化文件生成器 | low | light_or_standard | `skills/06_frontend/01_frontend_project_scaffold/SKILL.md` |
| 7 | frontend | `frontend.frontend_self_test` | 前端自测 | high | strict | `skills/06_frontend/12_frontend_self_test/SKILL.md` |
| 7 | frontend | `frontend.list_search_pagination` | 列表搜索筛选分页 | high | strict | `skills/06_frontend/09_list_search_pagination/SKILL.md` |
| 7 | frontend | `frontend.miniprogram_config_generator` | 小程序配置文件生成器 | high | strict | `skills/06_frontend/02_miniprogram_config_generator/SKILL.md` |
| 7 | frontend | `frontend.mobile_pc_adaptation` | 多端适配 | high | strict | `skills/06_frontend/11_mobile_pc_adaptation/SKILL.md` |
| 7 | frontend | `frontend.route_guard_permission` | 路由守卫与权限控制 | high | strict | `skills/06_frontend/03_route_guard_permission/SKILL.md` |
| 7 | frontend | `frontend.state_management` | 状态管理 | high | strict | `skills/06_frontend/04_state_management/SKILL.md` |
| 7 | frontend | `frontend.static_page_build` | 静态页面搭建 | high | strict | `skills/06_frontend/07_static_page_build/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.api_integration_plan` | 接口联调计划 | high | strict | `skills/07_integration_debugging/00_api_integration_plan/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.bug_root_cause_analysis` | Bug 根因分析 | high | strict | `skills/07_integration_debugging/06_bug_root_cause_analysis/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.cors_auth_debug` | 跨域与鉴权排查 | high | strict | `skills/07_integration_debugging/02_cors_auth_debug/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.data_mismatch_debug` | 数据不一致排查 | high | strict | `skills/07_integration_debugging/03_data_mismatch_debug/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.full_process_runthrough` | 完整业务流程跑通 | high | strict | `skills/07_integration_debugging/05_full_process_runthrough/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.network_error_debug` | 网络请求错误排查 | high | strict | `skills/07_integration_debugging/01_network_error_debug/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.payment_callback_debug` | 支付回调排查 | high | strict | `skills/07_integration_debugging/04_payment_callback_debug/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.regression_after_fix` | 修复后回归 | high | strict | `skills/07_integration_debugging/07_regression_after_fix/SKILL.md` |
| 8 | integration_debugging | `integration_debugging.systematic_debugging` | 系统性调试 | high | strict | `skills/07_integration_debugging/08_systematic_debugging/SKILL.md` |
| 9 | testing | `testing.api_test_cases` | 接口测试用例 | high | strict | `skills/08_testing/04_api_test_cases/SKILL.md` |
| 9 | testing | `testing.boundary_exception_cases` | 边界与异常用例 | high | strict | `skills/08_testing/02_boundary_exception_cases/SKILL.md` |
| 9 | testing | `testing.bug_report_template` | Bug 报告模板 | high | strict | `skills/08_testing/07_bug_report_template/SKILL.md` |
| 9 | testing | `testing.compatibility_test_cases` | 兼容性测试 | high | strict | `skills/08_testing/05_compatibility_test_cases/SKILL.md` |
| 9 | testing | `testing.functional_test_cases` | 功能测试用例 | high | strict | `skills/08_testing/01_functional_test_cases/SKILL.md` |
| 9 | testing | `testing.performance_test_plan` | 性能测试计划 | high | strict | `skills/08_testing/06_performance_test_plan/SKILL.md` |
| 9 | testing | `testing.permission_test_cases` | 权限测试用例 | high | strict | `skills/08_testing/03_permission_test_cases/SKILL.md` |
| 9 | testing | `testing.regression_test_suite` | 回归测试套件 | high | strict | `skills/08_testing/08_regression_test_suite/SKILL.md` |
| 9 | testing | `testing.release_acceptance_test` | 上线验收测试 | high | strict | `skills/08_testing/09_release_acceptance_test/SKILL.md` |
| 9 | testing | `testing.test_driven_development` | 测试驱动开发（TDD） | high | strict | `skills/08_testing/10_test_driven_development/SKILL.md` |
| 9 | testing | `testing.test_plan` | 测试计划 | high | strict | `skills/08_testing/00_test_plan/SKILL.md` |
| 10 | security | `security.admin_panel_security_check` | 后台管理安全检查 | high | strict | `skills/09_security/10_admin_panel_security_check/SKILL.md` |
| 10 | security | `security.auth_security_check` | 登录注册安全检查 | high | strict | `skills/09_security/01_auth_security_check/SKILL.md` |
| 10 | security | `security.deploy_server_security_check` | 部署与服务器安全检查 | high | strict | `skills/09_security/11_deploy_server_security_check/SKILL.md` |
| 10 | security | `security.full_security_audit` | 项目全量安全检查 | high | strict | `skills/09_security/00_full_security_audit/SKILL.md` |
| 10 | security | `security.log_error_security_check` | 日志与错误安全检查 | high | strict | `skills/09_security/12_log_error_security_check/SKILL.md` |
| 10 | security | `security.payment_security_check` | 支付与回调安全检查 | high | strict | `skills/09_security/09_payment_security_check/SKILL.md` |
| 10 | security | `security.rate_limit_idempotency_check` | 防刷与幂等安全 | high | strict | `skills/09_security/06_rate_limit_idempotency_check/SKILL.md` |
| 10 | security | `security.rbac_overpermission_check` | 权限与越权检查 | high | strict | `skills/09_security/03_rbac_overpermission_check/SKILL.md` |
| 10 | security | `security.security_acceptance_gate` | 上线安全门禁 | high | strict | `skills/09_security/13_security_acceptance_gate/SKILL.md` |
| 10 | security | `security.sensitive_data_check` | 敏感数据安全检查 | high | strict | `skills/09_security/08_sensitive_data_check/SKILL.md` |
| 10 | security | `security.sql_injection_check` | SQL 注入检查 | high | strict | `skills/09_security/04_sql_injection_check/SKILL.md` |
| 10 | security | `security.token_session_security` | Token 与会话安全 | high | strict | `skills/09_security/02_token_session_security/SKILL.md` |
| 10 | security | `security.upload_security_check` | 文件上传安全检查 | high | strict | `skills/09_security/07_upload_security_check/SKILL.md` |
| 10 | security | `security.xss_csrf_check` | XSS 与 CSRF 检查 | high | strict | `skills/09_security/05_xss_csrf_check/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.backend_deploy` | 后端打包部署 | high | strict | `skills/10_deployment_ops/04_backend_deploy/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.database_init_backup` | 数据库初始化与备份 | high | strict | `skills/10_deployment_ops/06_database_init_backup/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.docker_deploy` | Docker 部署 | high | strict | `skills/10_deployment_ops/05_docker_deploy/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.env_variables_config` | 环境变量配置 | high | strict | `skills/10_deployment_ops/01_env_variables_config/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.frontend_deploy` | 前端打包部署 | high | strict | `skills/10_deployment_ops/03_frontend_deploy/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.gray_release` | 灰度上线 | high | strict | `skills/10_deployment_ops/07_gray_release/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.nginx_ssl_domain` | 域名 SSL Nginx | high | strict | `skills/10_deployment_ops/02_nginx_ssl_domain/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.operation_runbook` | 运维手册 | high | strict | `skills/10_deployment_ops/10_operation_runbook/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.production_monitoring` | 生产监控 | high | strict | `skills/10_deployment_ops/09_production_monitoring/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.rollback_plan` | 回滚方案 | high | strict | `skills/10_deployment_ops/08_rollback_plan/SKILL.md` |
| 11 | deployment_ops | `deployment_ops.server_prepare` | 服务器准备 | high | strict | `skills/10_deployment_ops/00_server_prepare/SKILL.md` |
| 12 | iteration | `iteration.backlog_grooming` | 需求池维护 | high | strict | `skills/11_iteration/03_backlog_grooming/SKILL.md` |
| 12 | iteration | `iteration.feedback_triage` | 用户反馈归类 | high | strict | `skills/11_iteration/00_feedback_triage/SKILL.md` |
| 12 | iteration | `iteration.handover_docs` | 交付文档沉淀 | high | strict | `skills/11_iteration/05_handover_docs/SKILL.md` |
| 12 | iteration | `iteration.hotfix_workflow` | 线上紧急修复 | high | strict | `skills/11_iteration/02_hotfix_workflow/SKILL.md` |
| 12 | iteration | `iteration.release_notes` | 版本发布说明 | high | strict | `skills/11_iteration/04_release_notes/SKILL.md` |
| 12 | iteration | `iteration.version_planning` | 版本规划 | high | strict | `skills/11_iteration/01_version_planning/SKILL.md` |
| 13 | code_quality | `code_quality.code_review` | 代码审查 | high | strict | `skills/12_code_quality/00_code_review/SKILL.md` |
| 13 | code_quality | `code_quality.dependency_upgrade` | 依赖升级检查 | high | strict | `skills/12_code_quality/03_dependency_upgrade/SKILL.md` |
| 13 | code_quality | `code_quality.git_branch_commit` | Git 分支提交规范 | high | strict | `skills/12_code_quality/02_git_branch_commit/SKILL.md` |
| 13 | code_quality | `code_quality.observability_logs` | 可观测性与日志规范 | high | strict | `skills/12_code_quality/05_observability_logs/SKILL.md` |
| 13 | code_quality | `code_quality.performance_optimization` | 性能优化 | high | strict | `skills/12_code_quality/04_performance_optimization/SKILL.md` |
| 13 | code_quality | `code_quality.refactoring_plan` | 重构计划 | high | strict | `skills/12_code_quality/01_refactoring_plan/SKILL.md` |
| 14 | documentation | `documentation.doc_review_gate` | 文档质量检查门禁 | low | light_or_standard | `skills/13_documentation/03_doc_review_gate/SKILL.md` |
| 14 | documentation | `documentation.docs_index_generator` | docs/README.md 文档索引生成器 | low | light_or_standard | `skills/13_documentation/02_docs_index_generator/SKILL.md` |
| 14 | documentation | `documentation.docs_orchestrator` | docs 文档总控生成器 | high | strict | `skills/13_documentation/00_docs_orchestrator/SKILL.md` |
| 14 | documentation | `documentation.stage_doc_generator` | 阶段文档生成器 | high | strict | `skills/13_documentation/01_stage_doc_generator/SKILL.md` |
| 15 | project_startup_docs | `project_startup_docs.env_example_generator` | .env.example 生成器 | high | strict | `skills/14_project_startup_docs/01_env_example_generator/SKILL.md` |
| 15 | project_startup_docs | `project_startup_docs.getting_started_docs_generator` | docs/00_getting_started 文档生成器 | high | strict | `skills/14_project_startup_docs/02_getting_started_docs_generator/SKILL.md` |
| 15 | project_startup_docs | `project_startup_docs.project_startup_docs_generator` | 具体业务项目启动文档生成器 | high | strict | `skills/14_project_startup_docs/00_project_startup_docs_generator/SKILL.md` |
