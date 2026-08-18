from __future__ import annotations

import asyncio

from agents.qa_agent import (
    QAAgent,
    QueryIntent,
    format_history_text,
    normalize_history,
)
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing import Annotated, Any, NotRequired, TypedDict


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class ScriptedLLM:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def ainvoke(self, messages):
        text = "\n".join(str(m.content) for m in messages)
        self.prompts.append(text)
        return FakeResponse(self.responses.pop(0))


def test_normalize_and_format_history():
    turns = normalize_history([
        {"role": "user", "content": "差旅上限？"},
        {"role": "assistant", "content": "每天 500 元"},
        {"role": "user", "content": "需要审批吗？"},
    ])
    assert len(turns) == 3
    text = format_history_text(turns)
    assert "差旅上限" in text
    assert "每天 500 元" in text


def test_rewrite_uses_history_for_coreference():
    llm = ScriptedLLM([
        """{"resolved_question":"差旅报销是否需要提前审批？","queries":["差旅报销 提前审批"],"entities":["差旅报销"],"keywords":["审批"]}"""
    ])
    agent = object.__new__(QAAgent)
    agent.llm = llm
    rewritten = asyncio.run(agent._rewrite_query(
        "需要提前审批吗？",
        normalize_history([
            {"role": "user", "content": "差旅报销上限是多少？"},
            {"role": "assistant", "content": "每天 500 元，需提前审批。"},
        ]),
    ))
    assert rewritten["resolved_question"] == "差旅报销是否需要提前审批？"
    assert "对话历史" in llm.prompts[0]
    assert "差旅报销上限" in llm.prompts[0]


def test_answer_with_history_records_resolved_question():
    llm = ScriptedLLM([
        "factoid",
        '{"resolved_question":"差旅是否需要审批","queries":["差旅 审批"],"entities":["差旅"],"keywords":["审批"]}',
        "需要提前审批。",
    ])
    agent = object.__new__(QAAgent)
    agent.llm = llm
    agent.vector_store = None
    agent.knowledge_graph = None

    result = asyncio.run(agent.answer(
        "需要吗？",
        history=[
            {"role": "user", "content": "差旅要提前审批吗？"},
            {"role": "assistant", "content": "是的，需要提前审批。"},
        ],
        session_id="s1",
    ))
    assert result.intent == QueryIntent.FACTOID
    assert result.resolved_question == "差旅是否需要审批"
    assert result.session_id == "s1"
    assert any("指代消解后问题" in step for step in result.reasoning_steps)


def test_qa_graph_checkpointer_keeps_messages_across_turns():
    class GraphState(TypedDict, total=False):
        question: str
        history: list
        result: NotRequired[Any]
        messages: Annotated[list, add_messages]

    calls: list[list] = []

    class TinyAgent:
        async def answer(self, question, access_user=None, history=None, session_id=""):
            calls.append(list(history or []))
            from agents.qa_agent import QAResult, QueryIntent
            return QAResult(
                question=question,
                answer=f"答:{question}",
                contexts=[],
                intent=QueryIntent.FACTOID,
                confidence=0.5,
                session_id=session_id,
                resolved_question=question,
            )

    agent = TinyAgent()

    async def node(state: GraphState):
        history = []
        for msg in state.get("messages") or []:
            role = "user" if msg.type == "human" else "assistant"
            history.append({"role": role, "content": msg.content})
        result = await agent.answer(state["question"], history=history, session_id="t1")
        return {
            "result": result,
            "messages": [HumanMessage(content=state["question"]), AIMessage(content=result.answer)],
        }

    graph = StateGraph(GraphState)
    graph.add_node("answer", node)
    graph.set_entry_point("answer")
    graph.add_edge("answer", END)
    app = graph.compile(checkpointer=MemorySaver())

    cfg = {"configurable": {"thread_id": "user:s-demo"}}
    asyncio.run(app.ainvoke({"question": "第一问", "history": []}, config=cfg))
    asyncio.run(app.ainvoke({"question": "第二问", "history": []}, config=cfg))

    assert calls[0] == []
    assert len(calls[1]) == 2
    assert calls[1][0]["content"] == "第一问"
    assert calls[1][1]["content"] == "答:第一问"
