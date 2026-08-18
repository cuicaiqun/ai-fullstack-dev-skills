from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents.qa_agent import QAAgent, QueryIntent, RetrievedContext


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class ScriptedLLM:
    """按调用顺序返回预设内容。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0

    async def ainvoke(self, messages):
        if not self.responses:
            raise AssertionError("LLM received unexpected extra call")
        self.calls += 1
        return FakeResponse(self.responses.pop(0))


class FakeVectorStore:
    async def search(self, query: str, top_k: int = 5, where=None, access_user=None):
        return [
            (
                {
                    "content": f"向量命中: {query}",
                    "source": "handbook.md",
                    "metadata": {"doc_id": "d1"},
                },
                0.9,
            )
        ]


class FakeKnowledgeGraph:
    def __init__(self):
        self.search_calls: list[tuple[str, str | None]] = []
        self.neighbor_calls: list[tuple[str, str | None]] = []
        self.path_calls: list[tuple[str, str, str | None]] = []
        self.cypher_calls: list[str] = []

    async def search_entities(self, keyword: str, limit: int = 20, tenant_id=None):
        self.search_calls.append((keyword, tenant_id))
        return [
            {
                "name": keyword,
                "type": "Organization",
                "description": "图谱实体",
                "tenant_id": tenant_id,
            }
        ]

    async def get_neighbors(self, entity_name: str, hops: int = 2, tenant_id=None, limit: int = 50):
        self.neighbor_calls.append((entity_name, tenant_id))
        return [
            {
                "source": entity_name,
                "relations": ["RELATED_TO"],
                "target": "子公司",
                "target_type": "Organization",
                "target_desc": "关联公司",
                "tenant_id": tenant_id,
            }
        ]

    async def shortest_paths(
        self,
        name_a: str,
        name_b: str,
        tenant_id=None,
        max_hops: int = 5,
        limit: int = 3,
    ):
        self.path_calls.append((name_a, name_b, tenant_id))
        return []

    async def execute_cypher(self, cypher: str, params=None, **kwargs):
        self.cypher_calls.append(cypher)
        raise AssertionError("QA must not call free-form execute_cypher")


def _qa_agent(llm: ScriptedLLM) -> QAAgent:
    agent = object.__new__(QAAgent)
    agent.llm = llm
    agent.vector_store = FakeVectorStore()
    agent.knowledge_graph = FakeKnowledgeGraph()
    return agent


def test_answer_happy_path_uses_vector_and_graph_context():
    llm = ScriptedLLM([
        "factoid",
        '{"queries": ["腾讯是什么公司"], "entities": ["腾讯"], "keywords": ["公司"]}',
        "腾讯是一家互联网公司。[来源: handbook.md]",
    ])
    agent = _qa_agent(llm)

    result = asyncio.run(agent.answer("腾讯是什么？"))

    assert result.intent == QueryIntent.FACTOID
    assert "互联网公司" in result.answer
    assert any(c.retrieval_type == "vector" for c in result.contexts)
    assert any(c.retrieval_type == "graph" for c in result.contexts)
    assert result.confidence > 0
    assert result.reasoning_steps[-1] == "答案生成完成"
    assert llm.calls == 3  # intent + rewrite + answer；无 Cypher 生成
    assert agent.knowledge_graph.cypher_calls == []


def test_rewrite_query_accepts_fenced_json():
    agent = _qa_agent(ScriptedLLM([
        """```json
{"queries": ["改写后的查询"], "entities": ["实体A"], "keywords": ["关键词"]}
```"""
    ]))
    rewritten = asyncio.run(agent._rewrite_query("原始问题"))
    assert rewritten["queries"] == ["改写后的查询"]
    assert rewritten["entities"] == ["实体A"]


def test_rewrite_query_invalid_json_falls_back_to_original_question():
    agent = _qa_agent(ScriptedLLM(["不是合法JSON"]))
    rewritten = asyncio.run(agent._rewrite_query("原始问题"))
    assert rewritten == {
        "resolved_question": "原始问题",
        "queries": ["原始问题"],
        "entities": [],
        "keywords": [],
    }


def test_graph_retrieve_is_tenant_scoped_and_skips_free_cypher():
    agent = _qa_agent(ScriptedLLM([]))
    user = SimpleNamespace(tenant_id="tenant-a")
    contexts = asyncio.run(
        agent._graph_retrieve("问题", {"entities": ["A"], "keywords": []}, access_user=user)
    )
    assert contexts
    assert all(c.metadata.get("tenant_id") == "tenant-a" for c in contexts)
    assert agent.knowledge_graph.search_calls == [("A", "tenant-a")]
    assert agent.knowledge_graph.neighbor_calls == [("A", "tenant-a")]
    assert agent.knowledge_graph.cypher_calls == []


def test_classify_intent_unknown_defaults_to_factoid():
    agent = _qa_agent(ScriptedLLM(["完全不认识的标签"]))
    intent = asyncio.run(agent._classify_intent("随便问问"))
    assert intent == QueryIntent.FACTOID


def test_hybrid_rerank_boosts_relevant_and_deduplicates():
    contexts = [
        RetrievedContext(content="向量内容无关", source="v", score=0.8, retrieval_type="vector"),
        RetrievedContext(content="图谱内容腾讯公司介绍", source="g", score=0.8, retrieval_type="graph"),
        RetrievedContext(content="向量内容无关", source="v-dup", score=0.7, retrieval_type="vector"),
    ]
    agent = _qa_agent(ScriptedLLM([]))
    ranked = asyncio.run(agent._hybrid_rerank(contexts, query="腾讯公司"))
    assert len(ranked) == 2
    assert "腾讯" in ranked[0].content
