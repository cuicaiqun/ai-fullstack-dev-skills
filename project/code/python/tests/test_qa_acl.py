from __future__ import annotations

import asyncio

from agents.qa_agent import QAAgent, RetrievedContext
from api.auth.models import User


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class ScriptedLLM:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)

    async def ainvoke(self, messages):
        return FakeResponse(self.responses.pop(0))


class FakeVectorStore:
    def __init__(self):
        self.last_where = None

    async def search(self, query: str, top_k: int = 5, where=None, access_user=None):
        self.last_where = where
        hits = [
            (
                {
                    "content": "租户可见内容",
                    "source": "a.md",
                    "metadata": {
                        "doc_id": "d1",
                        "visibility": "tenant",
                        "tenant_id": "t1",
                        "owner_id": "u1",
                        "allowed_roles": "admin,member,viewer",
                    },
                },
                0.9,
            ),
            (
                {
                    "content": "其他租户机密",
                    "source": "b.md",
                    "metadata": {
                        "doc_id": "d2",
                        "visibility": "private",
                        "tenant_id": "t2",
                        "owner_id": "u9",
                    },
                },
                0.95,
            ),
        ]
        if access_user is not None:
            from api.auth.acl import can_access_document

            hits = [
                (doc, score)
                for doc, score in hits
                if can_access_document(access_user, doc.get("metadata") or {})
            ]
        return hits[:top_k]


def test_qa_answer_filters_inaccessible_vector_hits():
    store = FakeVectorStore()
    agent = object.__new__(QAAgent)
    agent.llm = ScriptedLLM([
        "factoid",
        '{"queries": ["机密"], "entities": [], "keywords": []}',
        "这是答案",
    ])
    agent.vector_store = store
    agent.knowledge_graph = None

    user = User(user_id="u1", username="alice", tenant_id="t1", role="member")
    result = asyncio.run(agent.answer("问什么", access_user=user))

    assert store.last_where is not None
    assert len(result.contexts) == 1
    assert result.contexts[0].content == "租户可见内容"


def test_qa_drops_unscoped_graph_for_non_admin():
    agent = object.__new__(QAAgent)
    agent.llm = ScriptedLLM([
        "factoid",
        '{"queries": ["q"], "entities": [], "keywords": []}',
        "答案",
    ])
    agent.vector_store = None
    agent.knowledge_graph = None

    async def empty_vector(rewritten, access_user=None):
        return []

    async def graph_without_acl(question, rewritten, access_user=None):
        return [
            RetrievedContext(
                content="图谱无租户标记",
                source="knowledge_graph",
                score=0.8,
                retrieval_type="graph",
                metadata={"mode": "legacy"},
            )
        ]

    agent._vector_retrieve = empty_vector  # type: ignore[method-assign]
    agent._graph_retrieve = graph_without_acl  # type: ignore[method-assign]

    user = User(user_id="u1", username="alice", tenant_id="t1", role="member")
    result = asyncio.run(agent.answer("问", access_user=user))
    assert result.contexts == []


def test_qa_keeps_same_tenant_graph_and_drops_cross_tenant():
    agent = object.__new__(QAAgent)
    agent.llm = ScriptedLLM([
        "factoid",
        '{"queries": ["q"], "entities": ["A"], "keywords": []}',
        "答案",
    ])
    agent.vector_store = None
    agent.knowledge_graph = None

    async def empty_vector(rewritten, access_user=None):
        return []

    async def graph_mixed(question, rewritten, access_user=None):
        return [
            RetrievedContext(
                content="本租户图谱",
                source="knowledge_graph",
                score=0.8,
                retrieval_type="graph",
                metadata={"tenant_id": "t1", "mode": "neighbors"},
            ),
            RetrievedContext(
                content="其他租户图谱",
                source="knowledge_graph",
                score=0.9,
                retrieval_type="graph",
                metadata={"tenant_id": "t2", "mode": "neighbors"},
            ),
        ]

    agent._vector_retrieve = empty_vector  # type: ignore[method-assign]
    agent._graph_retrieve = graph_mixed  # type: ignore[method-assign]

    user = User(user_id="u1", username="alice", tenant_id="t1", role="member")
    result = asyncio.run(agent.answer("问", access_user=user))
    assert len(result.contexts) == 1
    assert result.contexts[0].content == "本租户图谱"