"""Check local embedding dims + Chroma search after API ingest."""
from __future__ import annotations

import asyncio

from services.vector_store import VectorStoreService, _create_embeddings


async def main() -> None:
    emb = _create_embeddings()
    docs = await emb.aembed_documents(["唯一标记 XYZ-VEC-PROBE-991"])
    query = await emb.aembed_query("XYZ-VEC-PROBE-991")
    d, q = docs[0], query
    print("doc_dim", len(d), "query_dim", len(q))
    dn = sum(x * x for x in d) ** 0.5
    qn = sum(x * x for x in q) ** 0.5
    print("norms", round(dn, 4), round(qn, 4))
    if dn and qn:
        print("cosine", round(sum(a * b for a, b in zip(d, q)) / (dn * qn), 4))

    vs = VectorStoreService()
    await vs.init()
    print("stats", await vs.get_stats())
    for label in ("XYZ-VEC-PROBE-991", "VEC-API-ACCEPT-7742"):
        hits = await vs.search(label, top_k=3)
        print("search", label, [(round(s, 4), (h.get("content") or "")[:70]) for h, s in hits])


if __name__ == "__main__":
    asyncio.run(main())
