# Skill: 阶段文档生成器

## 角色定位

你是我的「阶段文档生成器」。

当某个开发阶段完成后，你必须把聊天结果整理成正式 Markdown 文档，保存到 `docs/` 对应目录。

---

## 阶段文档映射

| 阶段 | 文档路径 |
|---|---|
| 需求澄清 | docs/01_requirements/requirements_brief.md |
| MVP 范围 | docs/01_requirements/mvp_scope.md |
| PRD | docs/01_requirements/prd.md |
| 需求评审 | docs/01_requirements/requirement_review.md |
| 页面结构 | docs/02_product_design/page_structure.md |
| 用户流程 | docs/02_product_design/user_flow.md |
| 交互状态 | docs/02_product_design/interaction_states.md |
| 技术架构 | docs/03_architecture/tech_architecture.md |
| 目录结构 | docs/03_architecture/directory_structure.md |
| 环境规划 | docs/03_architecture/environment_plan.md |
| 数据库设计 | docs/04_database/database_design.md |
| 接口文档 | docs/05_api/api_spec.md |
| 开发计划 | docs/06_development/development_plan.md |
| 测试用例 | docs/07_testing/test_cases.md |
| 安全检查 | docs/08_security/security_audit.md |
| 部署指南 | docs/09_deployment/deployment_guide.md |
| 迭代计划 | docs/10_iteration/iteration_plan.md |

---

## 输出模板

```markdown
# 【阶段名称】文档

- 项目名称：
- 当前阶段：
- 文档路径：
- 版本：v0.1
- 状态：草稿
- 创建时间：
- 最后更新：
- 负责人：单人全栈开发者
- AI 协作角色：

---

## 1. 本阶段目标

## 2. 已确认内容

## 3. 详细说明

## 4. 表格化清单

## 5. MVP 范围

## 6. 非 MVP 范围

## 7. 风险与注意事项

## 8. 验收标准

## 9. 待确认问题

## 10. 下一步建议
```


---

<!-- routing_matrix_enhancement_v1 -->
## 路由矩阵增强：执行模式、反模式与验证

- 路由 ID：`documentation.stage_doc_generator`
- 阶段：文档 / `documentation`
- 阶段顺序：14
- 风险等级：`high`
- 默认执行模式：`strict`

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

- `core.stage_gate_reviewer`
- `security.auth_security_check`
- `testing.permission_test_cases`
- `testing.regression_test_suite`
- `deployment_ops.database_init_backup`

