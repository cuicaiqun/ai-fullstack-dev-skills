"""
Day 1 最小骨架：FastAPI 入口

目标（对照复现计划 Day 1～2）：
  1. 能启动服务
  2. GET  /api/health      — 健康检查
  3. POST /api/qa/ask      — 先 mock 返回，跑通请求/响应形状
  4. 理解：API 层只做接入，真正检索/生成以后再下沉到 graph/agent

后续演进：
  Day 3～5  — 换成真实 RAG
  Day 6～7  — 接入 LangGraph
  Day 8+    — rerank / grounding / CDC
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI

from app.models import (
    HealthResponse,
    QuestionRequest,
    QuestionResponse,
    SourceItem,
)

app = FastAPI(
    title="My RAG Interview Practice",
    description="秋招 AI 应用开发岗 · 分层复现练习项目",
    version="0.1.0-day1",
)


@app.get("/api/health", response_model=HealthResponse, tags=["系统"])
async def health() -> HealthResponse:
    """健康检查：先证明服务活着；以后再挂上 vector_store / llm 等依赖状态。"""
    return HealthResponse(
        status="ok",
        phase="phase0-skeleton",
        day=1,
        components={
            "api": "ok",
            "qa": "mock",
            "vector_store": "not_wired",
            "llm": "not_wired",
            "graph": "not_wired",
        },
    )


@app.post("/api/qa/ask", response_model=QuestionResponse, tags=["问答"])
async def ask_question(req: QuestionRequest) -> QuestionResponse:
    """智能问答（Day 1 为 mock）。

    对照真实项目 `code/python/api/main.py` 的 ask_question：
      - 校验请求体（此处由 Pydantic 完成）
      - 解析 / 生成 session_id
      - 调用 QA 工作流（此处尚未接入，先返回可解释的 mock）
      - 组装 answer / sources / grounded 等字段
    """
    session_id = (req.session_id or "").strip() or str(uuid.uuid4())
    question = req.question.strip()
    history_len = len(req.history or [])

    # Day 1：不调用 LLM / 向量库，只返回结构化 mock，方便联调与讲接口
    answer = (
        f"[MOCK Day1] 已收到问题：{question}\n"
        f"当前还没有接入检索与大模型。\n"
        f"历史轮次：{history_len}；session_id={session_id}\n"
        f"下一步（Day 3～5）：分块 → embedding → 检索 → 生成 → 返回 sources。"
    )

    return QuestionResponse(
        answer=answer,
        confidence=0.0,
        sources=[
            SourceItem(
                content="这是占位来源，真实项目会返回命中的文档片段。",
                source="mock://day1",
                score=0.0,
                retrieval_type="mock",
            )
        ],
        session_id=session_id,
        grounded=False,
        intent="unknown",
        mock=True,
        note=(
            "Day1 skeleton only. "
            f"server_time={datetime.now(timezone.utc).isoformat()}"
        ),
    )


@app.get("/", tags=["系统"])
async def root() -> dict[str, str]:
    return {
        "message": "My RAG Interview Practice is running",
        "health": "/api/health",
        "ask": "POST /api/qa/ask",
        "docs": "/docs",
    }
