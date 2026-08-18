"""Clear Chroma collection and verify real embed→upsert→search."""
from __future__ import annotations

import asyncio
import uuid

from agents.doc_parser_agent import DocType, DocumentChunk
from config import settings
from services.vector_store import VectorStoreService, _create_embeddings


async def main() -> None:
    print("embedding_backend", settings.embedding_backend)
    emb = _create_embeddings()
    print("emb", type(emb).__name__)
    vec = await emb.aembed_query("smoke")
    print("query_dim", len(vec), "norm", round(sum(x * x for x in vec) ** 0.5, 4))

    vs = VectorStoreService()
    await vs.init()
    # wipe stale/zero vectors so acceptance is clean
    ids = await vs._run_sync(vs._store.get, include=[])
    existing = ids.get("ids") or []
    if existing:
        await vs._run_sync(vs._store.delete, ids=existing)
        print("cleared", len(existing))
    print("stats_before", await vs.get_stats())

    marker = f"VEC-REAL-{uuid.uuid4().hex[:8]}"
    chunk = DocumentChunk(
        content=f"企业知识库向量验收文档，唯一标记 {marker}，验证 Chroma 真实写入与语义召回。",
        doc_id=f"accept-{marker}",
        chunk_index=0,
        doc_type=DocType.MARKDOWN,
        metadata={"source": "accept", "visibility": "public"},
    )
    added = await vs.add_chunks([chunk])
    print("added", added, "stats", await vs.get_stats())
    hits = await vs.search(marker, top_k=3)
    print("hits", [(round(score, 4), (doc.get("content") or "")[:90]) for doc, score in hits])
    assert added == 1
    assert hits and marker in (hits[0][0].get("content") or "")
    assert hits[0][1] > 0.2
    print("PASS")


if __name__ == "__main__":
    asyncio.run(main())
