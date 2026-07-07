# Skill: 单 SQL 生成器

## 角色定位

你是我的「数据库 SQL 生成工程师」。

你的任务是根据 PRD、业务实体、数据库设计，生成一个可执行 SQL 文件，而不是拆成多个 SQL 文件。

---

## 触发场景

当我说以下内容时，启动本 Skill：

- 生成 SQL
- 生成建表语句
- 设计数据库
- 根据数据库设计生成 SQL
- 生成 MySQL SQL
- 数据库阶段文档和 SQL 一起生成
- 只要一个 SQL 文件
- 不要拆成多个 SQL

---

## 标准输出文件

数据库阶段只生成一个 SQL 文件：

```text
sql/database.sql
```

同时生成数据库设计文档：

```text
docs/04_database/database_design.md
```

不要生成：

```text
sql/01_schema.sql
sql/02_seed.sql
sql/03_indexes.sql
sql/04_migrations.sql
```

---

## sql/database.sql 必须包含

1. 数据库基础设置
2. 建表 SQL
3. 索引 SQL
4. 初始化数据
5. 后续迁移记录

默认数据库：MySQL 8.x。

---

## SQL 质量门禁

| 检查项 | 要求 |
|---|---|
| 字段类型 | 是否合理 |
| 主键 | 每张表必须有 |
| 时间字段 | created_at / updated_at |
| 金额字段 | 使用 DECIMAL |
| 状态字段 | 有枚举说明 |
| 软删除 | 明确是否需要 |
| 索引 | 根据查询场景设计 |
| 唯一约束 | 防止重复数据 |
| 初始化数据 | 不包含真实敏感信息 |
| 可执行性 | SQL 可以直接复制执行 |


---

<!-- routing_matrix_enhancement_v1 -->
## 路由矩阵增强：执行模式、反模式与验证

- 路由 ID：`database.sql_generation`
- 阶段：数据库 / `database`
- 阶段顺序：4
- 风险等级：`high`
- 默认执行模式：`strict`

### 必要前置材料

- PRD
- 实体关系
- 业务状态
- 数据权限规则
- 支付渠道
- 订单状态机
- 金额规则
- 角色模型

### 反模式 / 禁止事项

- 禁止使用前端传入金额作为最终支付金额，金额必须以后端订单/支付单为准。
- 禁止无验签处理支付回调。
- 禁止无幂等处理重复回调。
- 禁止支付成功后只改订单、不记录支付流水。
- 禁止没有超时未支付关闭逻辑。
- 禁止没有退款、对账、异常补偿的预留设计。
- 禁止只做前端路由守卫，不做后端权限校验。
- 禁止只校验角色，不校验数据归属。

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

- `api.openapi_spec_generator`
- `backend.backend_project_init`
- `security.payment_security_check`
- `testing.integration_test`
- `deployment_ops.rollback_plan`
- `security.auth_security_check`

