# Day 1 实操清单（真实项目已跑通版）

> 假设本机已按 `project/CLAUDE.md` 启动：API 默认 **http://127.0.0.1:8080**  
> 今日目标：**讲清地图 + 打通接口形状**，不写新业务功能。

---

## A. 启动确认（5 分钟）

在浏览器或终端确认：

```bash
# 健康检查
curl -s http://127.0.0.1:8080/api/health | python -m json.tool

# Swagger
open http://127.0.0.1:8080/docs   # 或手动打开
```

记录你看到的依赖状态（写在下面）：

```text
vector_store: ________
knowledge_graph: ________
state_store: ________
embeddings: ________
```

**面试话术：** health 不只是 “活着”，还要暴露关键依赖是否可用，方便排障和降级。

---

## B. 对照三条链路打接口（30～40 分钟）

### 1) 问答链路（先会调）

若开启鉴权，先登录拿 token（以你环境实际 `/api/auth/login` 为准）：

```bash
# 示例：先看 Swagger 里 auth 相关接口字段
curl -s http://127.0.0.1:8080/api/qa/ask \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"question":"这个系统是做什么的？","session_id":"day1-demo"}' \
  | python -m json.tool
```

对照代码阅读顺序：

1. `code/python/api/main.py` → `ask_question`
2. `code/python/orchestrator/graph.py` → `_build_qa_graph`
3. `code/python/agents/qa_agent.py` → `answer`（可先扫类和方法名）

**自己填空：**

```text
请求字段：________________
响应字段：________________
session_id 有什么用：________________
sources / grounded 代表什么：________________
```

### 2) 入库链路（知道入口即可）

在 Swagger 找到上传/ingest 接口，或阅读：

- `upload_document`（`api/main.py`）
- `_build_ingest_graph`：`parse → extract → store_vectors → store_graph`

**自己填空：**

```text
为什么上传后可能先返回 task_id：________________
幂等（Idempotency-Key / 内容哈希）防止什么：________________
```

### 3) 更新链路（只建立概念）

阅读：

- `trigger_update`（`api/main.py`）
- `_build_update_graph`：`process → retry?`
- `services/cdc_processor.py` 文件头注释 / 类名

**自己填空：**

```text
更新和入库的差别：________________
为什么需要 retry / 幂等：________________
```

---

## C. 手绘架构（20 分钟，必须做）

不看资料，在纸上或 monologue 里画出：

```text
用户 → FastAPI → LangGraph → Agent → Vector/Graph/...
三条链路：入库 / 问答 / 更新
```

然后打开 `notes/architecture.md` 对照，缺什么补什么。

---

## D. 5 分钟口述（15 分钟）

用 `notes/day01_oral.md` + `architecture.md` 第 6 节：

1. 先计时讲一遍（可看稿）
2. 再脱稿讲一遍
3. 用下面 4 题自问自答

- API 和 Agent 为什么拆开？
- 问答为什么常用 POST？
- 没有检索只调 LLM 有什么问题？
- 健康检查为什么要返回依赖状态？

---

## E. Day1 完成标准（全部勾上才进入 Day2）

- [ ] `/api/health` 能解释每个字段大致含义
- [ ] 能说明 `POST /api/qa/ask` 的输入输出
- [ ] 能手绘四层架构 + 三条链路
- [ ] 每条链路能指出 ≥2 个源码文件
- [ ] 5 分钟项目介绍可以脱稿讲完
- [ ] 已实现 / 部分实现 / 设计目标 能各举 1 例

---

## F. 今日笔记模板（复制到 progress 或问题清单）

```markdown
### Day1 记录 YYYY-MM-DD

**我用大白话理解的系统：**
>

**三条链路一句话：**
- 入库：
- 问答：
- 更新：

**今天打通的接口：**
-

**卡点 / 问题：**
- Q:
  我的猜想：
  待验证：

**明天 Day2：**
- 把问答链路从 API 追到 QAAgent.answer 的调用栈
- 标注每个函数“输入/输出/副作用”
```
