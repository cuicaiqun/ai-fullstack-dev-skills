from __future__ import annotations

import asyncio

from agents.doc_parser_agent import DocType, DocumentChunk
from agents.knowledge_extract_agent import ExtractionResult, KnowledgeExtractAgent


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        return FakeResponse(self.content)


def _agent_with_llm(content: str) -> KnowledgeExtractAgent:
    agent = object.__new__(KnowledgeExtractAgent)
    agent.llm = FakeLLM(content)
    return agent


def test_extract_happy_path_parses_entities_and_relations():
    payload = """
    {
      "entities": [
        {"name": "腾讯", "type": "Organization", "description": "互联网公司"},
        {"name": "微信", "type": "Product", "description": "即时通讯"}
      ],
      "relations": [
        {"head": "微信", "relation": "developed_by", "tail": "腾讯", "confidence": 0.97}
      ],
      "events": [
        {"trigger": "发布", "type": "ProductLaunch", "participants": ["腾讯", "微信"]}
      ]
    }
    """
    agent = _agent_with_llm(payload)
    result = asyncio.run(agent.extract_single("腾讯开发了微信", chunk_id="c1"))

    assert len(result.entities) == 2
    assert result.entities[0].name == "腾讯"
    assert result.relations[0].relation == "developed_by"
    assert result.relations[0].confidence == 0.97
    assert result.events[0].trigger == "发布"
    assert result.source_chunk_id == "c1"


def test_extract_accepts_fenced_json_block():
    fenced = """```json
{"entities": [{"name": "Neo4j", "type": "Technology"}], "relations": [], "events": []}
```"""
    agent = _agent_with_llm(fenced)
    result = agent._parse_response(fenced, "chunk-fenced")

    assert [e.name for e in result.entities] == ["Neo4j"]
    assert result.source_chunk_id == "chunk-fenced"


def test_extract_invalid_json_falls_back_to_empty_result():
    agent = _agent_with_llm("这不是 JSON {{{")
    result = agent._parse_response("这不是 JSON {{{", "chunk-bad")

    assert result == ExtractionResult(
        entities=[],
        relations=[],
        events=[],
        source_chunk_id="chunk-bad",
    )


def test_extract_deduplicates_entities_across_chunks():
    agent = _agent_with_llm("")
    chunk = DocumentChunk(
        content="重复实体",
        doc_id="doc",
        chunk_index=0,
        doc_type=DocType.TEXT,
    )

    async def fake_extract(text, source_id):
        from agents.knowledge_extract_agent import Entity, Relation

        return ExtractionResult(
            entities=[Entity(name="腾讯", type="Organization")],
            relations=[Relation(head="微信", relation="developed_by", tail="腾讯")],
            events=[],
            source_chunk_id=source_id,
        )

    agent._extract_from_text = fake_extract  # type: ignore[method-assign]
    results = asyncio.run(agent.extract([chunk, chunk]))

    assert len(results) == 2
    assert len(results[0].entities) == 1
    assert results[1].entities == []
    assert len(results[0].relations) == 1
    assert results[1].relations == []
