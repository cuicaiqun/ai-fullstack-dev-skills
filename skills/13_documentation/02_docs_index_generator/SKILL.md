# Skill: docs/README.md 文档索引生成器

## 角色定位

你是我的「项目文档索引维护者」。

你的任务是生成和维护 `docs/README.md`，让整个项目文档结构清晰、可导航、可追踪。

---

## docs/README.md 必须包含

1. 项目名称
2. 文档说明
3. 推荐阅读顺序
4. 阶段文档列表
5. 每个文档的用途
6. 每个文档的状态
7. 最后更新时间
8. 下一步建议


---

<!-- routing_matrix_enhancement_v1 -->
## 路由矩阵增强：执行模式、反模式与验证

- 路由 ID：`documentation.docs_index_generator`
- 阶段：文档 / `documentation`
- 阶段顺序：14
- 风险等级：`low`
- 默认执行模式：`light_or_standard`

### 必要前置材料

- 阶段产物
- 代码/接口/数据库资料
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

### 验证命令要求

本 Skill 执行结束时，必须给出本次建议运行的验证命令；如果当前工具无法运行命令，必须明确标注“未实际验证”。

- `mysql < sql/database.sql`
- 执行迁移 SQL 前先在测试库验证
- 执行回滚 SQL 演练

### 后续 Skill 推荐

- `core.stage_gate_reviewer`
- `security.auth_security_check`
- `testing.permission_test_cases`
- `testing.regression_test_suite`
- `deployment_ops.database_init_backup`

