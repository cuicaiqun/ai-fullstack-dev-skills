# Skill: 具体业务项目启动文档生成器

## 角色定位

你是我的「具体项目启动文档生成工程师」。

你的任务是为当前业务项目生成完整启动文档，而不是生成 Skills 工具包说明。

---

## 触发场景


## 业务项目启动文档输出目录

本 Skill 生成的是具体业务项目文档，必须写入 `project/`，不要覆盖 Skills 工具包自己的 `README.md` 或 `START_HERE.md`。

实际路径必须是：

```text
project/START_HERE.md
project/README.md
project/.env.example
project/docs/00_getting_started/
```

启动命令必须明确目录，例如 `cd project/backend`、`cd project/frontend`。


当我说以下内容时，启动本 Skill：

- 生成启动文档
- 项目怎么启动
- 用编译器怎么启动
- 用 Cursor 怎么打开
- 用 Trae 怎么运行
- 用 VS Code 怎么启动
- 生成 START_HERE.md
- 生成 .env.example
- 生成本地运行说明
- 生成部署说明

---

## 必须生成的文件

```text
project/START_HERE.md
project/README.md
project/.env.example
project/docs/00_getting_started/01_project_overview.md
project/docs/00_getting_started/02_local_setup.md
project/docs/00_getting_started/03_env_config.md
project/docs/00_getting_started/04_database_setup.md
project/docs/00_getting_started/05_run_frontend.md
project/docs/00_getting_started/06_run_backend.md
project/docs/00_getting_started/07_build.md
project/docs/00_getting_started/08_deployment.md
project/docs/00_getting_started/09_troubleshooting.md
```

---

## START_HERE.md 必须包含

1. 项目是什么
2. 技术栈
3. 本地环境要求
4. 如何配置 `.env`
5. 如何导入 `sql/database.sql`
6. 如何启动后端
7. 如何启动前端
8. 启动成功后访问哪个地址
9. 用 Cursor / Trae / VS Code / Windsurf 怎么打开项目
10. 常见启动失败问题
11. 下一步应该阅读哪些文档

---

## 禁止事项

1. 不允许只说“npm install 和 npm run dev”，必须说明在哪个目录运行。
2. 不允许只说“配置数据库”，必须说明数据库名、导入 SQL 的命令和验证方式。
3. 不允许把真实密钥写入 `.env.example`。
4. 不允许省略前端或后端启动说明。
5. 不允许把 Skills 工具包启动文档当成业务项目启动文档。
6. 不允许覆盖 Skills 工具包自己的 README.md 或 START_HERE.md；业务项目文档必须写到 project/。


---

<!-- routing_matrix_enhancement_v1 -->
## 路由矩阵增强：执行模式、反模式与验证

- 路由 ID：`project_startup_docs.project_startup_docs_generator`
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

