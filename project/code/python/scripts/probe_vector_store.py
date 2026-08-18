"""One-off vector store acceptance probe."""
from __future__ import annotations

import asyncio

from agents.doc_parser_agent import DocType, DocumentChunk
from config import settings
from services.vector_store import VectorStoreService, _create_embeddings


async def main() -> None:
    print("embedding_backend", settings.embedding_backend)
    emb = _create_embeddings()
    print("emb", type(emb).__name__)
    vs = VectorStoreService()
    await vs.init()
    print("chroma ready", vs._store is not None, await vs.get_stats())
    chunk = DocumentChunk(
        content="向量库可用性探测：唯一标记 XYZ-VEC-PROBE-991 GraphRAG",
        doc_id="probe991",
        chunk_index=0,
        doc_type=DocType.MARKDOWN,
        metadata={"source": "probe", "visibility": "public"},
    )
    n = await vs.add_chunks([chunk])
    print("added", n, "stats", await vs.get_stats())
    hits = await vs.search("XYZ-VEC-PROBE-991", top_k=3)
    print("hits", [(h[0]["content"][:50], round(h[1], 4)) for h in hits])


if __name__ == "__main__":
    asyncio.run(main())
