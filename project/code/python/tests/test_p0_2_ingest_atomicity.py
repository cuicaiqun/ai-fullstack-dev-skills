"""P0-2：入库原子性判定、文档索引状态、pgvector 删除。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from agents.doc_parser_agent import DocType, DocumentChunk
from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent
from services.ingest_storage import assess_ingest_storage
from services.state_store import DocumentIndexStatus, MemoryStateStore
from services.vector_store import VectorStoreService


def test_assess_ingest_storage_rejects_vector_failure():
    ok, err = assess_ingest_storage(
        {
            "chunks": [object()],
            "vectors_ok": False,
            "vectors_error": "chroma down",
            "store_ok": False,
            "store_error": "chroma down",
        }
    )
    assert not ok
    assert "chroma" in err


def test_assess_ingest_storage_rejects_embeddings_skipped():
    ok, err = assess_ingest_storage(
        {
            "chunks": [object()],
            "vectors_ok": False,
            "vectors_skipped": True,
            "vectors_error": "embeddings unavailable",
        }
    )
    assert not ok
    assert "embed" in err.lower() or "unavailable" in err.lower()


def test_assess_ingest_storage_accepts_ok_state():
    ok, err = assess_ingest_storage(
        {
            "chunks": [object()],
            "vectors_ok": True,
            "vectors_stored": 2,
            "graph_required": False,
            "store_ok": True,
        }
    )
    assert ok
    assert err == ""


def test_document_index_pending_then_ready_or_failed():
    store = MemoryStateStore()
    store.init()
    rec = store.begin_document_index("doc-a", tenant_id="t1", source_path="/a.md")
    assert rec.status == DocumentIndexStatus.PENDING.value
    assert rec.version == 1
    assert not store.is_document_ready("doc-a")

    store.finalize_document_index("doc-a", 1, DocumentIndexStatus.FAILED, "boom")
    assert store.get_document_index("doc-a").status == "failed"
    assert not store.is_document_ready("doc-a")

    rec2 = store.begin_document_index("doc-a", tenant_id="t1", source_path="/a.md")
    assert rec2.version == 2
    store.finalize_document_index("doc-a", 2, DocumentIndexStatus.READY)
    assert store.is_document_ready("doc-a")


def test_pgvector_delete_by_doc_id_uses_backend_path():
    store = VectorStoreService()
    store._backend = "pgvector"
    store._store = object()

    async def fake_run_sync(fn, *args, **kwargs):
        assert fn == store._delete_pgvector_by_doc_id
        assert args[0] == "doc-xyz"
        return 3

    store._run_sync = fake_run_sync  # type: ignore[method-assign]
    deleted = asyncio.run(store.delete_by_doc_id("doc-xyz"))
    assert deleted == 3


def test_delete_by_doc_id_fails_when_disconnected():
    store = VectorStoreService()
    store._store = None
    with pytest.raises(RuntimeError, match="not connected"):
        asyncio.run(store.delete_by_doc_id("doc-xyz"))


def test_graph_delete_by_source_fails_when_disconnected():
    from services.knowledge_graph import KnowledgeGraphService

    kg = KnowledgeGraphService()
    with pytest.raises(RuntimeError, match="not connected"):
        asyncio.run(kg.delete_by_source("/x.md", tenant_id="t1"))


def test_update_create_stamps_acl_metadata(tmp_path, monkeypatch):
    target = tmp_path / "policy.md"
    target.write_text("hello acl", encoding="utf-8")

    from api.auth.models import DocumentACL
    from api.auth.store import AuthStore

    auth = AuthStore(db_path=str(tmp_path / "auth.db"))
    auth.init()
    monkeypatch.setattr("api.auth.store.auth_store", auth)

    class FakeParser:
        async def parse(self, file_path: str):
            from agents.doc_parser_agent import DocParserAgent

            doc_id = DocParserAgent._make_doc_id(file_path)
            return [
                DocumentChunk(
                    content="hello",
                    doc_id=doc_id,
                    chunk_index=0,
                    doc_type=DocType.MARKDOWN,
                    metadata={},
                )
            ]

    class FakeVS:
        embeddings_available = True
        added = []

        async def add_chunks(self, chunks):
            self.added.append(chunks)
            return len(chunks)

    vs = FakeVS()
    state = MemoryStateStore()
    state.init()
    agent = KnowledgeUpdateAgent(doc_parser=FakeParser(), vector_store=vs, state_store=state)
    result = asyncio.run(
        agent.process_change(
            DocumentChange(file_path=str(target), change_type=ChangeType.CREATED)
        )
    )
    assert result.success
    assert vs.added
    meta = vs.added[0][0].metadata
    assert meta.get("tenant_id")
    assert meta.get("doc_id")
    assert state.is_document_ready(meta["doc_id"])
    acl = auth.get_document_acl(meta["doc_id"])
    assert isinstance(acl, DocumentACL)
    assert acl.source_path


def test_ingest_graph_marks_vectors_not_ok_on_failure():
    from unittest.mock import AsyncMock

    from orchestrator.graph import _build_ingest_graph

    vs = MagicMock()
    vs.embeddings_available = True
    vs.add_chunks = AsyncMock(side_effect=RuntimeError("chroma down"))

    chunk = MagicMock()
    chunk.doc_id = "d1"
    doc_parser = MagicMock()
    doc_parser.parse_batch = AsyncMock(return_value=[chunk])
    extractor = MagicMock()
    extractor.extract = AsyncMock(return_value=[])

    graph = _build_ingest_graph(doc_parser, extractor, vs, None)
    out = asyncio.run(graph.ainvoke({"file_paths": ["/tmp/a.md"]}))
    assert out.get("vectors_ok") is False
    assert out.get("store_ok") is False
    ok, _ = assess_ingest_storage(out)
    assert not ok


def test_is_document_searchable_legacy_and_status():
    store = MemoryStateStore()
    store.init()
    assert store.is_document_searchable("never-indexed") is True
    store.begin_document_index("doc-p", tenant_id="t1")
    assert store.is_document_ready("doc-p") is False
    assert store.is_document_searchable("doc-p") is False
    rec = store.get_document_index("doc-p")
    assert rec is not None
    store.finalize_document_index("doc-p", rec.version, DocumentIndexStatus.READY)
    assert store.is_document_searchable("doc-p") is True


class _QueryCollection:
    def __init__(self, rows):
        self.rows = rows

    def query(self, **kwargs):
        docs, metas, dists = [], [], []
        for content, meta, dist in self.rows:
            docs.append(content)
            metas.append(meta)
            dists.append(dist)
        return {"documents": [docs], "metadatas": [metas], "distances": [dists]}

    def upsert(self, **kwargs):
        return None

    def count(self):
        return len(self.rows)


class _Embed:
    async def aembed_documents(self, texts):
        return [[0.1] for _ in texts]

    async def aembed_query(self, text):
        return [0.1]


def test_search_filters_pending_failed_and_state_store():
    state = MemoryStateStore()
    state.init()
    state.begin_document_index("doc-ready", tenant_id="t1")
    ready_rec = state.get_document_index("doc-ready")
    state.finalize_document_index("doc-ready", ready_rec.version, DocumentIndexStatus.READY)
    state.begin_document_index("doc-pending", tenant_id="t1")

    vs = VectorStoreService()
    vs._backend = "chroma"
    vs._embeddings = _Embed()
    vs.set_doc_searchable_checker(state.document_search_gate)
    vs._store = _QueryCollection(
        [
            ("ready hit", {"doc_id": "doc-ready", "source": "a.md", "index_status": "pending"}, 0.1),
            ("pending hit", {"doc_id": "doc-pending", "source": "b.md", "index_status": "pending"}, 0.2),
            ("failed meta", {"doc_id": "doc-x", "source": "c.md", "index_status": "failed"}, 0.3),
            ("legacy", {"doc_id": "legacy-1", "source": "d.md"}, 0.4),
        ]
    )

    results = asyncio.run(vs.search("q", top_k=10))
    contents = [doc["content"] for doc, _ in results]
    assert contents == ["ready hit", "legacy"]


def test_graph_hits_filter_pending_source_not_entity_name():
    from services.knowledge_graph import KnowledgeGraphService

    state = MemoryStateStore()
    state.init()
    rec = state.begin_document_index(
        "doc-g", tenant_id="t1", source_path="/pending.md"
    )
    # pending → deny by path
    kg = KnowledgeGraphService()
    kg.set_doc_searchable_checker(state.document_search_gate)

    entity_rows = [
        {"name": "Alice", "source": "/pending.md"},
        {"name": "Bob", "source": "/legacy.md"},
    ]
    assert [r["name"] for r in kg._filter_searchable(entity_rows)] == ["Bob"]

    neighbor_rows = [
        {
            "source": "Alice",
            "target": "Corp",
            "start_source": "/pending.md",
            "neighbor_source": "/legacy.md",
        },
        {
            "source": "Bob",
            "target": "Corp",
            "start_source": "/legacy.md",
            "neighbor_source": "/legacy.md",
        },
    ]
    kept = kg._filter_searchable(neighbor_rows)
    assert [r["source"] for r in kept] == ["Bob"]

    state.finalize_document_index("doc-g", rec.version, DocumentIndexStatus.READY)
    assert [r["name"] for r in kg._filter_searchable(entity_rows)] == ["Alice", "Bob"]



def test_graph_search_filters_non_ready_sources():
    from services.knowledge_graph import KnowledgeGraphService

    state = MemoryStateStore()
    state.init()
    rec = state.begin_document_index(
        "doc-ready", tenant_id="t1", source_path="/ready.md"
    )
    state.finalize_document_index("doc-ready", rec.version, DocumentIndexStatus.READY)
    state.begin_document_index("doc-pending", tenant_id="t1", source_path="/pending.md")

    kg = KnowledgeGraphService()
    kg.set_doc_searchable_checker(state.document_search_gate)
    rows = [
        {"name": "ok", "source": "/ready.md"},
        {"name": "pending", "source": "/pending.md"},
        {"name": "legacy", "source": ""},
        {"name": "unknown-path", "source": "/never-indexed.md"},
    ]
    kept = kg._filter_searchable(rows)
    assert [r["name"] for r in kept] == ["ok", "legacy", "unknown-path"]

    neighbor_rows = [
        {"source": "ok", "start_source": "/ready.md", "neighbor_source": "/pending.md"},
        {"source": "ok", "start_source": "/ready.md", "neighbor_source": "/never-indexed.md"},
    ]
    kept_n = kg._filter_searchable(neighbor_rows)
    assert len(kept_n) == 1
    assert kept_n[0]["neighbor_source"] == "/never-indexed.md"


def test_graph_filters_pending_source_not_entity_name():
    from services.knowledge_graph import KnowledgeGraphService

    state = MemoryStateStore()
    state.init()
    rec = state.begin_document_index("doc-g", tenant_id="t1", source_path="/pending.md")
    kg = KnowledgeGraphService()
    kg.set_doc_searchable_checker(state.document_search_gate)

    entity_rows = [
        {"name": "待丢弃", "source": "/pending.md"},
        {"name": "遗留", "source": "/legacy.md"},
    ]
    assert [r["name"] for r in kg._filter_searchable(entity_rows)] == ["遗留"]

    neighbor_rows = [
        {
            "source": "待丢弃",  # entity name, not a path
            "target": "遗留",
            "start_source": "/pending.md",
            "neighbor_source": "/legacy.md",
        }
    ]
    assert kg._filter_searchable(neighbor_rows) == []

    state.finalize_document_index("doc-g", rec.version, DocumentIndexStatus.READY)
    assert [r["name"] for r in kg._filter_searchable(entity_rows)] == ["待丢弃", "遗留"]
    assert kg._filter_searchable(neighbor_rows) == neighbor_rows
