"""
问答 Agent — 混合检索 (Vector + Graph) + 多跳推理 + 答案生成

核心能力:
  1. 意图识别 & 查询改写（支持多轮指代消解）
  2. 向量检索 (语义相似度)
  3. 图谱检索 (Cypher 查询 / 子图遍历)
  4. 混合排序 & 重排序
  5. 基于检索结果的答案生成（带引用来源）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from observability.llm import build_chat_openai

MAX_HISTORY_TURNS = 6  # 最多保留最近 6 轮（user+assistant）


class QueryIntent(str, Enum):
    FACTOID = "factoid"           # 事实型问题
    ANALYTICAL = "analytical"     # 分析型问题
    COMPARATIVE = "comparative"   # 对比型问题
    PROCEDURAL = "procedural"     # 流程型问题
    EXPLORATORY = "exploratory"   # 探索型问题


@dataclass
class ChatTurn:
    role: str  # user | assistant
    content: str


@dataclass
class RetrievedContext:
    content: str
    source: str
    score: float
    retrieval_type: str  # "vector" | "graph" | "hybrid"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QAResult:
    question: str
    answer: str
    contexts: list[RetrievedContext]
    intent: QueryIntent
    confidence: float
    reasoning_steps: list[str] = field(default_factory=list)
    resolved_question: str = ""
    session_id: str = ""
    grounded: bool = True
    grounding_notes: list[str] = field(default_factory=list)


INTENT_PROMPT = """\
你是一个查询意图分类器。根据用户问题（可参考对话历史），返回意图类别（只返回类别名）：
- factoid: 事实型（谁/什么/哪里/何时）
- analytical: 分析型（为什么/怎么理解）
- comparative: 对比型（A和B有什么区别）
- procedural: 流程型（怎么做/步骤）
- exploratory: 探索型（有哪些/概述）
"""

QUERY_REWRITE_PROMPT = """\
你是一个查询改写与指代消解专家。结合对话历史，将用户当前问题改写为适合检索的形式。
要求：
1. 做指代消解：把“它/上述/那个/这个公司”等替换为历史中的具体实体或主题
2. 给出 resolved_question：消歧后的完整独立问句
3. 提取核心实体和关键词，生成 1-3 个检索查询
4. 返回 JSON:
{"resolved_question": "完整问句", "queries": ["查询1", "查询2"], "entities": ["实体1"], "keywords": ["关键词1"]}
只返回 JSON，不要其他文字。
"""

ANSWER_PROMPT = """\
你是一个专业的企业知识问答助手。根据检索到的上下文信息与对话历史回答用户问题。

要求：
1. 答案必须严格基于提供的上下文，不要编造上下文中没有的事实
2. 如果上下文信息不足，明确告知用户「知识库中未找到足够依据」
3. 引用信息来源时使用 [来源 N]（N 为上下文编号）
4. 如果涉及多个信息源，综合分析后给出结论
5. 结合对话历史理解追问与指代，保持专业、准确、简洁
"""


def normalize_history(history: list[Any] | None, limit: int = MAX_HISTORY_TURNS * 2) -> list[ChatTurn]:
    """将 dict / ChatTurn / LangChain message 归一化为 ChatTurn 列表。"""
    if not history:
        return []
    turns: list[ChatTurn] = []
    for item in history:
        if isinstance(item, ChatTurn):
            role, content = item.role, item.content
        elif isinstance(item, dict):
            role = str(item.get("role") or "").lower()
            content = str(item.get("content") or "")
        else:
            role = str(getattr(item, "type", getattr(item, "role", ""))).lower()
            content = str(getattr(item, "content", "") or "")
            if role in {"human", "user"}:
                role = "user"
            elif role in {"ai", "assistant"}:
                role = "assistant"
        if role not in {"user", "assistant"} or not content.strip():
            continue
        turns.append(ChatTurn(role=role, content=content.strip()))
    return turns[-limit:]


def format_history_text(history: list[ChatTurn]) -> str:
    if not history:
        return "（无历史）"
    lines = []
    for turn in history:
        label = "用户" if turn.role == "user" else "助手"
        lines.append(f"{label}: {turn.content}")
    return "\n".join(lines)


class QAAgent:
    """
    问答 Agent

    工作流:
      query → intent_classify → rewrite(指代消解) → parallel_retrieve → rerank → generate_answer
    """

    def __init__(
        self,
        vector_store: Any = None,
        knowledge_graph: Any = None,
    ) -> None:
        self.llm = build_chat_openai(component="qa_agent")
        self.vector_store = vector_store
        self.knowledge_graph = knowledge_graph

    # ── public API ───────────────────────────────────────────

    async def answer(
        self,
        question: str,
        access_user: Any = None,
        history: list[Any] | None = None,
        session_id: str = "",
    ) -> QAResult:
        """完整问答流程。history 用于多轮指代消解；access_user 用于文档 ACL。"""
        turns = normalize_history(history)
        intent = await self._classify_intent(question, turns)
        rewritten = await self._rewrite_query(question, turns)
        resolved = str(rewritten.get("resolved_question") or question).strip() or question

        vector_contexts = await self._vector_retrieve(rewritten, access_user=access_user)
        graph_contexts = await self._graph_retrieve(resolved, rewritten, access_user=access_user)

        all_contexts = await self._hybrid_rerank(
            vector_contexts + graph_contexts,
            query=resolved or question,
        )
        if access_user is not None:
            from api.auth.acl import filter_contexts_by_acl

            user_tenant = getattr(access_user, "tenant_id", None)
            filtered: list[RetrievedContext] = []
            for ctx in all_contexts:
                meta = ctx.metadata or {}
                ctx_tenant = meta.get("tenant_id")
                # P0-1：严禁跨租户图谱/向量上下文
                if ctx_tenant and user_tenant and ctx_tenant != user_tenant:
                    continue
                if meta.get("doc_id") or meta.get("visibility") or meta.get("owner_id"):
                    if filter_contexts_by_acl(access_user, [ctx]):
                        filtered.append(ctx)
                elif ctx_tenant and ctx_tenant == user_tenant:
                    # 租户隔离的图谱命中（无文档级 ACL metadata）对同租户用户可见
                    filtered.append(ctx)
                elif not ctx_tenant and getattr(access_user, "role", "") == "admin":
                    # 兼容旧数据：无 tenant 标记的图谱结果仅 admin
                    filtered.append(ctx)
            all_contexts = filtered
        top_contexts = all_contexts[:8]

        answer_text, reasoning = await self._generate_answer(
            question,
            top_contexts,
            intent,
            history=turns,
            resolved_question=resolved,
        )

        from services.grounding import check_answer_grounding

        grounding = check_answer_grounding(answer_text, top_contexts)
        confidence = self._calc_confidence(top_contexts)
        if not grounding.grounded:
            confidence = min(confidence, 0.35)
            reasoning = list(reasoning) + [f"引用校验未通过: {','.join(grounding.notes)}"]
            if settings.qa_refuse_ungrounded:
                answer_text = (
                    "抱歉，当前回答无法通过引用校验，系统不能将其作为可信依据返回。"
                    "请上传相关文档后重试，或换一种问法。"
                )
                confidence = min(confidence, 0.05)
                reasoning = list(reasoning) + ["已强制拒答: grounded=false"]

        return QAResult(
            question=question,
            answer=answer_text,
            contexts=top_contexts,
            intent=intent,
            confidence=confidence,
            reasoning_steps=reasoning,
            resolved_question=resolved,
            session_id=session_id,
            grounded=grounding.grounded,
            grounding_notes=list(grounding.notes),
        )

    # ── intent classification ────────────────────────────────

    async def _classify_intent(self, question: str, history: list[ChatTurn] | None = None) -> QueryIntent:
        history_text = format_history_text(history or [])
        messages = [
            SystemMessage(content=INTENT_PROMPT),
            HumanMessage(content=f"对话历史:\n{history_text}\n\n当前问题: {question}"),
        ]
        resp = await self.llm.ainvoke(messages)
        raw = resp.content.strip().lower()
        for intent in QueryIntent:
            if intent.value in raw:
                return intent
        return QueryIntent.FACTOID

    # ── query rewriting ──────────────────────────────────────

    async def _rewrite_query(self, question: str, history: list[ChatTurn] | None = None) -> dict:
        import json
        history_text = format_history_text(history or [])
        messages = [
            SystemMessage(content=QUERY_REWRITE_PROMPT),
            HumanMessage(content=f"对话历史:\n{history_text}\n\n当前问题: {question}"),
        ]
        resp = await self.llm.ainvoke(messages)
        try:
            cleaned = resp.content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                raise json.JSONDecodeError("not object", cleaned, 0)
            data.setdefault("resolved_question", question)
            data.setdefault("queries", [data.get("resolved_question") or question])
            data.setdefault("entities", [])
            data.setdefault("keywords", [])
            return data
        except (json.JSONDecodeError, IndexError):
            return {
                "resolved_question": question,
                "queries": [question],
                "entities": [],
                "keywords": [],
            }

    # ── vector retrieval ─────────────────────────────────────

    async def _vector_retrieve(self, rewritten: dict, access_user: Any = None) -> list[RetrievedContext]:
        if not self.vector_store:
            return []

        where = None
        if access_user is not None:
            from api.auth.acl import build_chroma_access_where

            where = build_chroma_access_where(access_user)

        contexts: list[RetrievedContext] = []
        for query in rewritten.get("queries", []):
            results = await self.vector_store.search(
                query,
                top_k=5,
                where=where,
                access_user=access_user,
            )
            for doc, score in results:
                contexts.append(RetrievedContext(
                    content=doc.get("content", ""),
                    source=doc.get("source", "vector_store"),
                    score=score,
                    retrieval_type="vector",
                    metadata=doc.get("metadata", {}),
                ))
        return contexts

    # ── graph retrieval ──────────────────────────────────────

    async def _graph_retrieve(
        self,
        question: str,
        rewritten: dict,
        access_user: Any = None,
    ) -> list[RetrievedContext]:
        """租户隔离的参数化图谱检索（P0-1）；不再执行 LLM 自由 Cypher（P0-5）。"""
        if not self.knowledge_graph:
            return []

        import logging

        from services.knowledge_graph import resolve_tenant_id

        tid = resolve_tenant_id(
            getattr(access_user, "tenant_id", None) if access_user is not None else None
        )
        names: list[str] = []
        for key in ("entities", "keywords"):
            for item in rewritten.get(key) or []:
                name = str(item).strip()
                if name and name not in names:
                    names.append(name)
        if not names and question.strip():
            names = [question.strip()[:64]]

        contexts: list[RetrievedContext] = []
        seen: set[tuple] = set()
        log = logging.getLogger(__name__)

        for name in names[:10]:
            try:
                hits = await self.knowledge_graph.search_entities(
                    name, limit=5, tenant_id=tid
                )
                for hit in hits:
                    key = ("entity", hit.get("name"), tid)
                    if key in seen:
                        continue
                    seen.add(key)
                    contexts.append(
                        RetrievedContext(
                            content=(
                                f"{hit.get('name', '')} ({hit.get('type', '')}): "
                                f"{hit.get('description', '')}"
                            ),
                            source="knowledge_graph",
                            score=0.78,
                            retrieval_type="graph",
                            metadata={**hit, "tenant_id": tid, "mode": "search"},
                        )
                    )
                neighbors = await self.knowledge_graph.get_neighbors(
                    name, hops=2, tenant_id=tid
                )
                for record in neighbors:
                    key = (
                        "edge",
                        record.get("source"),
                        record.get("target"),
                        tuple(record.get("relations") or []),
                        tid,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    content = (
                        f"{record.get('source', '')} "
                        f"--[{', '.join(record.get('relations', []))}]--> "
                        f"{record.get('target', '')} "
                        f"({record.get('target_type', '')}): "
                        f"{record.get('target_desc', '')}"
                    )
                    contexts.append(
                        RetrievedContext(
                            content=content,
                            source="knowledge_graph",
                            score=0.8,
                            retrieval_type="graph",
                            metadata={**record, "tenant_id": tid, "mode": "neighbors"},
                        )
                    )
            except Exception:
                log.exception("Graph retrieve failed for entity=%s tenant=%s", name, tid)
                continue

        for i in range(len(names)):
            for j in range(i + 1, min(i + 3, len(names))):
                try:
                    paths = await self.knowledge_graph.shortest_paths(
                        names[i], names[j], tenant_id=tid
                    )
                    for rec in paths:
                        nodes = rec.get("node_names") or []
                        rels = rec.get("rel_types") or []
                        path_str = ""
                        for k, node in enumerate(nodes):
                            path_str += str(node)
                            if k < len(rels):
                                path_str += f" --[{rels[k]}]--> "
                        key = ("path", path_str, tid)
                        if key in seen or not path_str:
                            continue
                        seen.add(key)
                        contexts.append(
                            RetrievedContext(
                                content=f"推理路径: {path_str}",
                                source="knowledge_graph",
                                score=0.85,
                                retrieval_type="graph",
                                metadata={
                                    "from": names[i],
                                    "to": names[j],
                                    "tenant_id": tid,
                                    "mode": "path",
                                },
                            )
                        )
                except Exception:
                    log.exception(
                        "Graph path failed %s -> %s tenant=%s",
                        names[i],
                        names[j],
                        tid,
                    )
                    continue

        return contexts

    # ── hybrid reranking ─────────────────────────────────────

    async def _hybrid_rerank(
        self,
        contexts: list[RetrievedContext],
        query: str = "",
    ) -> list[RetrievedContext]:
        """查询-文档相似度重排 + 轻量类型加成（替代硬编码 ×1.2）。"""
        from services.rerank import rerank_scored_items

        embeddings = None
        if self.vector_store is not None and getattr(self.vector_store, "embeddings_available", False):
            embeddings = self.vector_store.embeddings

        return await rerank_scored_items(
            query,
            contexts,
            get_content=lambda c: c.content,
            get_type=lambda c: c.retrieval_type,
            get_base_score=lambda c: c.score,
            set_score=lambda c, s: setattr(c, "score", s),
            embeddings=embeddings,
        )

    # ── answer generation ────────────────────────────────────

    async def _generate_answer(
        self,
        question: str,
        contexts: list[RetrievedContext],
        intent: QueryIntent,
        history: list[ChatTurn] | None = None,
        resolved_question: str = "",
    ) -> tuple[str, list[str]]:
        context_text = "\n\n".join(
            f"[来源 {i+1}: {c.source} | 类型: {c.retrieval_type} | 分数: {c.score:.2f}]\n{c.content}"
            for i, c in enumerate(contexts)
        )
        history_text = format_history_text(history or [])
        resolved = resolved_question or question
        reasoning_steps = [
            f"识别问题意图: {intent.value}",
            f"指代消解后问题: {resolved}",
            f"检索到 {len(contexts)} 条相关上下文",
            f"向量检索: {sum(1 for c in contexts if c.retrieval_type == 'vector')} 条",
            f"图谱检索: {sum(1 for c in contexts if c.retrieval_type == 'graph')} 条",
        ]

        if not contexts:
            msg = (
                "知识库中未检索到与该问题相关的内容，无法基于企业内部知识作答。"
                "请确认相关文档已入库，或换一种问法后重试。"
            )
            reasoning_steps.append("检索为空，拒绝无根据作答")
            return msg, reasoning_steps

        system_prompt = ANSWER_PROMPT
        user_prompt = (
            f"对话历史:\n{history_text}\n\n"
            f"上下文信息:\n{context_text}\n\n"
            f"用户原问题: {question}\n"
            f"消歧后问题: {resolved}"
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        resp = await self.llm.ainvoke(messages)
        reasoning_steps.append("答案生成完成")
        return resp.content, reasoning_steps

    @staticmethod
    def _calc_confidence(contexts: list[RetrievedContext]) -> float:
        if not contexts:
            return 0.0
        avg_score = sum(c.score for c in contexts) / len(contexts)
        return min(avg_score, 1.0)
