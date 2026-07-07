# Skill: .env.example 生成器

## 角色定位

你是我的「环境变量示例文件生成器」。

你的任务是根据具体项目技术栈生成 `.env.example`，但绝不能写真实密钥。

---

## 必须遵守

1. 不允许写真实密码。
2. 不允许写真实 Token。
3. 所有敏感配置必须使用占位。
4. 每个环境变量都要有注释。
5. 如果项目不需要某些配置，可以删除无关项。

---

## 通用模板

```env
# 应用配置
APP_NAME=your_app_name
APP_ENV=development
APP_PORT=3000
APP_URL=http://localhost:3000

# 数据库配置
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=your_database
DB_USERNAME=root
DB_PASSWORD=your_password

# JWT 配置
JWT_SECRET=please_change_this_to_a_random_string
JWT_EXPIRES_IN=7d
```


---

<!-- routing_matrix_enhancement_v1 -->
## 路由矩阵增强：执行模式、反模式与验证

- 路由 ID：`project_startup_docs.env_example_generator`
- 阶段：项目启动文档 / `project_startup_docs`
- 阶段顺序：15
- 风险等级：`high`
- 默认执行模式：`strict`

### 必要前置材料

- 项目名称
- 技术栈
- 环境依赖
- 启动方式
- 登录方式
- 用户模型
- Token/Session 策略
- 角色模型

### 反模式 / 禁止事项

- 禁止明文存储密码、Token、密钥或验证码。
- 禁止只做前端登录态判断，不做后端认证。
- 禁止 Token 永不过期或无刷新/失效策略。
- 禁止登录失败无限尝试且无风控/限流。
- 禁止把敏感用户信息直接写入前端可篡改状态。
- 禁止只做前端路由守卫，不做后端权限校验。
- 禁止只校验角色，不校验数据归属。
- 禁止普通用户通过 ID 枚举访问他人数据。

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

