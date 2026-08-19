# 架构地图（Day 1）

> 目标：闭卷也能画出来，并讲 5 分钟。  
> 对照源码：`project/code/python/`  
> 练习项目：`project/my_rag_interview/`

---

## 1. 一句话定位

面向企业知识库的 **可引用、可更新** 智能问答系统：

- 用户上传业务文档
- 系统解析、切分、写入向量库 / 知识图谱
- 用户提问时做检索增强生成（RAG），返回答案和来源
- 文档变更后做增量更新，而不是每次全量重建

**目标用户（面试说法）：** 企业内部员工 / 客服 / 运营等需要基于私有文档准确问答的人。

---

## 2. 分层架构（先记这一张）

```text
┌─────────────────────────────────────────────┐
│  客户端（浏览器静态页 / curl / 其它服务）      │
└──────────────────┬──────────────────────────┘
                   │ HTTP (JSON)
                   ▼
┌─────────────────────────────────────────────┐
│  API 层  FastAPI                             │
│  code/python/api/main.py                     │
│  - 参数校验（Pydantic）                        │
│  - 鉴权 / 限流 / 幂等 Key                      │
│  - 把请求转成工作流输入，把结果转成 JSON         │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  编排层  LangGraph                            │
│  code/python/orchestrator/graph.py           │
│  - ingest / qa / update 三张图                 │
│  - 节点顺序、条件分支、失败重试                 │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Agent 层                                    │
│  code/python/agents/                         │
│  - DocParserAgent        解析与分块            │
│  - KnowledgeExtractAgent 实体关系抽取          │
│  - QAAgent               检索 + 生成           │
│  - KnowledgeUpdateAgent  增量更新              │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  服务 / 存储层  code/python/services/         │
│  - VectorStoreService   向量写入/检索          │
│  - KnowledgeGraphService / graph_rag         │
│  - rerank / grounding / cdc_processor        │
│  - state_store（文档状态、幂等、检索门禁）      │
└─────────────────────────────────────────────┘
```

### 为什么要拆 API / Graph / Agent / Store？

| 层 | 职责 | 不管什么 |
|----|------|----------|
| API | 协议、鉴权、校验、HTTP 错误码 | 不管分块算法细节 |
| Graph | 步骤顺序与分支 | 不管具体用哪个向量库 API |
| Agent | 业务能力（问答、更新） | 不管 HTTP 路径长什么样 |
| Store | 持久化与检索 | 不管 prompt 怎么写 |

面试一句话：

> API 是门面，Graph 是工序，Agent 是工人，Store 是仓库。

---

## 3. 三条主链路（必须能画）

### 链路 A：文档入库 Ingest

```text
POST /api/ingest（上传文件）
  → 安全保存文件（upload_security）
  → 幂等检查（state_store + Idempotency-Key/内容哈希）
  → 异步任务 or 同步执行
  → LangGraph ingest:
        parse → extract → store_vectors → store_graph
  → 返回 chunks/entities/relations 统计 或 task_id
```

| 步骤 | 真实代码位置 |
|------|----------------|
| 上传接口 | `api/main.py` → `upload_document` |
| 解析分块 | `agents/doc_parser_agent.py` |
| 知识抽取 | `agents/knowledge_extract_agent.py` |
| 向量写入 | `services/vector_store.py` |
| 图谱写入 | `services/knowledge_graph.py` |
| 图编排 | `orchestrator/graph.py` → `_build_ingest_graph` |

**为什么需要入库？**  
LLM 本身没有你的私有文档；不入库就无法「先检索再回答」。

---

### 链路 B：智能问答 QA

```text
POST /api/qa/ask
  body: { question, session_id?, history? }
  → 鉴权 get_current_user
  → 限流（用户级 / 租户级）
  → LangGraph qa（可带 checkpointer 多轮记忆）
        → QAAgent.answer
              意图识别 / 查询改写
              → 向量检索 + 图谱检索
              → 重排序 rerank
              → grounding 约束
              → LLM 生成 + sources
  → QuestionResponse: answer, confidence, sources, grounded...
```

| 步骤 | 真实代码位置 |
|------|----------------|
| 问答接口 | `api/main.py` → `ask_question` |
| QA 图 | `orchestrator/graph.py` → `_build_qa_graph` |
| 问答逻辑 | `agents/qa_agent.py` |
| 向量检索 | `services/vector_store.py` |
| 图谱检索 | `services/graph_rag.py` |
| 重排 | `services/rerank.py` |
| 落地约束 | `services/grounding.py` |

**为什么问答常用 POST 不是 GET？**

- 请求体可包含较长 `question`、`history`，不适合全部放 query string
- 语义上是「提交一次问答任务并产生结果」，不是简单获取固定资源
- 可避免敏感问题出现在 URL / 代理日志里

---

### 链路 C：文档更新 Update / CDC

```text
文件变更（API 触发 / Watchdog / Kafka 事件）
  → 统一成变更对象 / CDCEvent
  → 判断 INSERT / UPDATE / DELETE
  → LangGraph update:
        process → (失败则 retry) → END
  → KnowledgeUpdateAgent:
        删旧向量/图谱片段 → 按需重新解析入库
  → 幂等（event_id）避免重复消费写炸
```

| 步骤 | 真实代码位置 |
|------|----------------|
| 手动触发更新 | `api/main.py` → `trigger_update` |
| 更新图 | `orchestrator/graph.py` → `_build_update_graph` |
| 更新 Agent | `agents/knowledge_update_agent.py` |
| CDC | `services/cdc_processor.py` |
| 状态 / 幂等 | `services/state_store.py` |

**为什么不能每次全量重建？**

- 文档量大时成本高、延迟高
- 只需处理变化部分（增量）
- 但要解决：重复事件、失败重试、多存储一致性

---

## 4. 真实项目 vs 我的复现（进度）

| 能力 | 真实项目 | 我的练习 `my_rag_interview` |
|------|----------|-----------------------------|
| FastAPI 入口 | 有 | Day1 已有 |
| `/api/health` | 有（含依赖探测） | Day1 简化版 |
| `/api/qa/ask` | 真检索 + LLM | Day1 **mock** |
| 鉴权 JWT / ACL | 有 | 未做（Day12） |
| 向量 RAG | 有 | Day3～5 |
| LangGraph | 有 | Day6～7 |
| Rerank / Grounding | 有 | Day8～9 |
| CDC / 增量更新 | 有（部分生产能力仍在加固） | Day10～11 |

---

## 5. 已实现 vs 设计目标（面试一定要会区分）

回答时主动分层，避免被问穿：

| 状态 | 含义 | 例子 |
|------|------|------|
| 已实现 | 代码在，本地/测试能说明白 | FastAPI 三组接口、ingest 图节点、QAAgent 主流程 |
| 部分实现 | 接线了但企业级验收未齐 | CDC、多存储强一致、部分 E2E |
| 设计目标 | ROADMAP 里的方向 | 完整企业工作台、完整 K8s/KMS 等 |
| 未验证 | 文档有、环境未跑通 | 某些真实依赖联调项 |

具体以 `project/ROADMAP.md` 为准，面试说：

> 我按代码和 ROADMAP 区分「能演示的」和「规划中的」，不把设计当已交付。

---

## 6. 5 分钟口述稿（建议背熟结构，不要死背原文）

### 0:00–1:00 业务问题

> 我做的是企业知识库问答。员工有大量内部文档，直接问大模型会幻觉，而且文档会更新。  
> 所以系统要解决三件事：把文档变成可检索知识、回答时给出依据、文档变更后增量同步。

### 1:00–4:00 架构与三条链路

> 整体四层：FastAPI 接入、LangGraph 编排、Agent 业务、Vector/Graph 等存储。  
>  
> 第一条入库：上传后 parse → extract → 写向量 → 写图谱。  
> 第二条问答：提问后鉴权限流，再走 QA 工作流，向量+图谱检索，重排和 grounding，最后生成带 sources 的答案。  
> 第三条更新：监听或接收变更事件，算 diff，删旧写新，并用 event_id 保证幂等。  
>  
> 我复现时先做最小 RAG 闭环，再加编排和更新，而不是一上来上全套中间件。

### 4:00–5:00 现状与取舍

> 当前练习项目 Day1 只跑通了 health 和 mock 问答接口，先把请求响应和分层边界站稳。  
> 接下来会依次补真实检索、LangGraph、质量与增量更新。  
> 真实仓库里还有多租户、CDC、部署加固等，我会按「已实现/部分实现」来讲，不夸大。

---

## 7. Day1 自检清单

- [ ] 能手绘分层图（API → Graph → Agent → Store）
- [ ] 能画出入库 / 问答 / 更新三条链路
- [ ] 能说出每条链路至少 2 个对应源码文件
- [ ] 能解释为什么 API 与 Agent 要拆开
- [ ] 能解释问答为什么常用 POST
- [ ] 本地能访问 `/api/health` 与 `POST /api/qa/ask`
