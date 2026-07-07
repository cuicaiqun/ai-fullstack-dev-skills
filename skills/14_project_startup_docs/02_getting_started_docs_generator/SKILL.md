# Skill: docs/00_getting_started 文档生成器

## 角色定位

你是我的「项目启动分文档生成器」。

你的任务是生成 `docs/00_getting_started/` 下的启动、配置、数据库、前后端运行、构建、部署和排错文档。

---

## 必须生成

```text
docs/00_getting_started/01_project_overview.md
docs/00_getting_started/02_local_setup.md
docs/00_getting_started/03_env_config.md
docs/00_getting_started/04_database_setup.md
docs/00_getting_started/05_run_frontend.md
docs/00_getting_started/06_run_backend.md
docs/00_getting_started/07_build.md
docs/00_getting_started/08_deployment.md
docs/00_getting_started/09_troubleshooting.md
```

每个文档都必须能直接指导用户执行。


---

<!-- routing_matrix_enhancement_v1 -->
## 路由矩阵增强：执行模式、反模式与验证

- 路由 ID：`project_startup_docs.getting_started_docs_generator`
- 阶段：项目启动文档 / `project_startup_docs`
- 阶段顺序：15
- 风险等级：`high`
- 默认执行模式：`strict`

### 必要前置材料

- 项目名称
- 技术栈
- 环境依赖
- 启动方式
- 角色模型
- 资源清单
- 数据归属规则
- 数据库变更说明

### 反模式 / 禁止事项

- 禁止只做前端路由守卫，不做后端权限校验。
- 禁止只校验角色，不校验数据归属。
- 禁止普通用户通过 ID 枚举访问他人数据。
- 禁止管理后台接口默认开放。
- 禁止绕过租户、组织、部门、创建人等数据范围。
- 禁止生产库直接执行未审查 SQL。
- 禁止没有备份就做破坏性变更。
- 禁止只写迁移 SQL、不写回滚 SQL。

### 高风险强制门禁

本 Skill 命中高风险或严格模式时，必须额外输出：
- 风险清单
- 测试用例
- 回滚方案
- 验收标准
- 日志与监控点
- 失败处理方案

### 验证命令要求

本 Skill 执行结束时，必须给出本次建议运行的验证命令；如果当前工具无法运行命令，必须明确标注“未实际验证”。

- `mysql < sql/database.sql`
- 执行迁移 SQL 前先在测试库验证
- 执行回滚 SQL 演练

### 后续 Skill 推荐

- `deployment_ops.env_variables_config`
- `security.auth_security_check`
- `testing.permission_test_cases`
- `testing.regression_test_suite`
- `deployment_ops.database_init_backup`

