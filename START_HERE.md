# START HERE：一键启动项目黄金路径


## 0. 先确认真实项目放哪里

本 Skills 包是规则和模板，不是业务项目代码仓库。

当你让 AI 创建真实项目时，默认目录必须是：

```text
project/
├── backend/
├── frontend/
├── docs/
├── sql/
├── tests/
└── scripts/
```

后端代码写入 `project/backend/`，前端代码写入 `project/frontend/`。不要把真实业务代码写进 `skills/05_backend/`、`skills/06_frontend/`、`templates/` 或 `examples/`。


你不需要先读完 144 个 Skill。先在下面选择你当前的情况，然后按对应路径启动。

## A. 我只有一个想法

路径：

```text
需求澄清 → MVP 范围 → PRD → 页面/流程 → 架构 → 数据库 → API → 后端 → 前端 → 联调 → 测试 → 安全 → 部署
```

建议启动：

```text
启动 core.project_context_collector，先把项目背景、目标用户、核心业务、平台端和约束收集完整。
```

## B. 我已经有 PRD

路径：

```text
PRD 评审 → 页面功能规格 → 架构 → 数据库 → API → 开发 → 测试
```

建议启动：`requirements.requirements_review`，然后进入 `architecture.tech_stack_selection`；如果要确定前端组件库，再进入 `architecture.frontend_ui_library_selection`。

## C. 我已经有页面图 / 原型

路径：

```text
页面信息架构 → 用户流程 → 交互状态 → API 字段 → 前端组件 → 联调
```

建议启动：`product_design.information_architecture`。


## C2. 我要确定前端组件库

路径：

```text
项目类型 → 前端技术栈 → 端类型 → 组件需求 → UI 组件库选型 → 前端初始化 → 基础组件封装
```

建议启动：`architecture.frontend_ui_library_selection`。

## D. 我已经有数据库

路径：

```text
表结构审查 → 状态/索引/权限 → API 契约 → 后端模块 → 测试数据
```

建议启动：`database.table_design` 或 `database.migration_seed_plan`。

## E. 我已经有代码但跑不起来

路径：

```text
复现 → 缩小范围 → 日志/证据 → 假设 → 最小修复 → 回归测试 → 防复发
```

建议启动：`integration_debugging.systematic_debugging`。不要直接乱改代码。

## F. 我要上线

路径：

```text
安全检查 → 环境变量 → 构建 → 部署 → 数据备份 → 冒烟验证 → 监控 → 回滚预案
```

建议启动：`security.full_security_audit`，通过后进入 `deployment_ops.server_prepare`。

## G. 我要修 Bug

路径：

```text
Bug 报告 → 复现路径 → 根因分析 → 最小修复 → 回归 → 发布说明
```

建议启动：`integration_debugging.bug_root_cause_analysis` 或 `integration_debugging.systematic_debugging`。

## H. 我要重构

路径：

```text
问题定位 → 风险评估 → 测试保护 → 小步重构 → 回归 → 文档更新
```

建议启动：`code_quality.refactoring_plan`。

## I. 我要做支付 / 权限 / 上传 / 数据库变更

这些都是高风险任务，必须进入严格模式。先读：

```text
HARD_GATES.md
skill_routing_matrix.json
```

然后选择对应 Skill，并强制输出风险、测试、回滚、验收、日志监控和失败处理。


## J. 我要创建真实前端和后端项目

路径：

```text
创建 project/ 工作区 → 后端写入 project/backend/ → 前端写入 project/frontend/ → 文档写入 project/docs/ → SQL 写入 project/sql/database.sql
```

建议启动：先执行 `architecture.repo_structure_standard` 确认目录结构，然后进入 `backend.backend_project_init` 和 `frontend.frontend_project_init`。

强制规则：真实代码不要写入 Skills 包的 `skills/` 目录，`skills/05_backend/` 和 `skills/06_frontend/` 只是技能说明，不是业务代码目录。
