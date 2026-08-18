from __future__ import annotations

import asyncio

from agents.doc_parser_agent import DocType, DocumentChunk
from services.vector_store import VectorStoreService


class FakeEmbeddings:
    async def aembed_documents(self, texts):
        return [[float(index)] for index, _ in enumerate(texts)]

    async def aembed_query(self, text):
        return [0.5]


class FakeChromaCollection:
    def __init__(self):
        self.upsert_call = None

    def upsert(self, **kwargs):
        self.upsert_call = kwargs

    def query(self, **kwargs):
        assert kwargs["query_embeddings"] == [[0.5]]
        return {
            "documents": [["匹配的企业知识"]],
            "metadatas": [[{"source": "handbook.md", "doc_id": "doc-1"}]],
            "distances": [[0.2]],
        }

    def count(self):
        return 1


def test_chroma_writes_searches_and_reports_real_count():
    store = VectorStoreService()
    store._backend = "chroma"
    store._store = FakeChromaCollection()
    store._embeddings = FakeEmbeddings()

    chunk = DocumentChunk(
        content="企业知识库支持向量检索。",
        doc_id="doc-1",
        chunk_index=0,
        doc_type=DocType.MARKDOWN,
        metadata={"source": "handbook.md"},
    )

    assert asyncio.run(store.add_chunks([chunk])) == 1
    assert store._store.upsert_call["ids"] == ["doc-1#chunk-0"]
    assert store._store.upsert_call["metadatas"][0]["doc_type"] == "markdown"

    results = asyncio.run(store.search("如何检索企业知识？"))
    assert results == [
        (
            {
                "content": "匹配的企业知识",
                "source": "handbook.md",
                "metadata": {"source": "handbook.md", "doc_id": "doc-1"},
            },
            0.8,
        )
    ]
    assert asyncio.run(store.get_stats()) == {
        "backend": "chroma",
        "total_vectors": 1,
        "collection": "knowledge_chunks",
    }
