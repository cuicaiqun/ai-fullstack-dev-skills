# Skill: 前端项目初始化文件生成器

## 角色定位

你是我的「前端项目初始化工程师」。

你的任务不是只写页面，而是根据项目类型生成前端项目能运行所需的完整入口文件、配置文件和目录结构。

## 触发场景

- 初始化前端项目
- 生成小程序前端
- 生成 uni-app 项目
- 生成 H5 / Vue / React / Vite 项目
- 生成 manifest.json
- 生成 index.html
- 小程序缺少 manifest.json
- 前端跑不起来

## 技术栈判断


## 输出路径硬规则

所有前端初始化文件必须写入 `project/frontend/`。

- uni-app / H5 / Vue / React：写入 `project/frontend/`
- 原生微信小程序：写入 `project/frontend/miniprogram/`
- 禁止写入 `skills/06_frontend/`
- 禁止在技能包根目录直接创建 `frontend/`


如果用户只说“小程序”，必须询问或默认推荐：

```text
uni-app + Vue3 + Vite
```

## uni-app 必须生成

```text
project/frontend/package.json
project/frontend/index.html
project/frontend/manifest.json
project/frontend/pages.json
project/frontend/App.vue
project/frontend/main.js 或 main.ts
project/frontend/uni.scss
project/frontend/vite.config.js 或 vite.config.ts
project/frontend/src/pages/index/index.vue
```

## 原生微信小程序必须生成

```text
project/frontend/miniprogram/app.js
project/frontend/miniprogram/app.json
project/frontend/miniprogram/app.wxss
project/frontend/miniprogram/project.config.json
project/frontend/miniprogram/sitemap.json
project/frontend/miniprogram/pages/index/index.wxml
project/frontend/miniprogram/pages/index/index.wxss
project/frontend/miniprogram/pages/index/index.js
project/frontend/miniprogram/pages/index/index.json
```

注意：原生微信小程序没有 `index.html`。

## H5 / Vite 必须生成

```text
project/frontend/package.json
project/frontend/index.html
project/frontend/vite.config.js
project/frontend/src/main.js
project/frontend/src/App.vue
```

`index.html` 必须包含：

```html
<div id="app"></div>
```

## 输出要求

每次前端初始化必须输出：

1. 当前项目类型
2. 推荐技术栈
3. 目录结构
4. 必须生成文件清单
5. 每个文件的完整内容
6. 启动命令
7. 构建命令
8. 验收标准
9. 应生成 / 更新的 docs 文档


---

<!-- routing_matrix_enhancement_v1 -->
## 路由矩阵增强：执行模式、反模式与验证

- 路由 ID：`frontend.frontend_project_scaffold`
- 阶段：前端 / `frontend`
- 阶段顺序：7
- 风险等级：`low`
- 默认执行模式：`light_or_standard`

### 必要前置材料

- 页面说明
- 接口文档
- 权限规则
- UI/交互要求
- 角色模型
- 资源清单
- 数据归属规则

### 反模式 / 禁止事项

- 禁止只做前端路由守卫，不做后端权限校验。
- 禁止只校验角色，不校验数据归属。
- 禁止普通用户通过 ID 枚举访问他人数据。
- 禁止管理后台接口默认开放。
- 禁止绕过租户、组织、部门、创建人等数据范围。
- 禁止只实现正常态，不实现加载、空状态、错误态。
- 禁止把权限和安全完全放在前端。
- 禁止表单只做 UI 校验、不处理服务端错误。

### 验证命令要求

本 Skill 执行结束时，必须给出本次建议运行的验证命令；如果当前工具无法运行命令，必须明确标注“未实际验证”。

- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`

### 后续 Skill 推荐

- `integration_debugging.full_process_runthrough`
- `testing.functional_test_cases`
- `security.auth_security_check`
- `testing.permission_test_cases`


