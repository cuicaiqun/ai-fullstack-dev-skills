from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agents.doc_parser_agent import DocParserAgent, DocType, DocumentChunk
from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent


class FakeParser:
    async def parse(self, file_path: str):
        doc_id = DocParserAgent._make_doc_id(file_path)
        return [
            DocumentChunk(
                content=f"content of {os.path.basename(file_path)}",
                doc_id=doc_id,
                chunk_index=0,
                doc_type=DocType.MARKDOWN,
                metadata={"source": file_path},
            )
        ]


class FakeVectorStore:
    def __init__(self):
        self.added = []
        self.deleted = []

    async def add_chunks(self, chunks):
        self.added.append(chunks)
        return len(chunks)

    async def delete_by_doc_id(self, doc_id: str):
        self.deleted.append(doc_id)
        return 2


class FakeGraph:
    def __init__(self):
        self.deleted_sources = []
        self.deleted_tenants = []

    async def delete_by_source(self, source: str, tenant_id=None):
        self.deleted_sources.append(source)
        self.deleted_tenants.append(tenant_id)


def test_kafka_consumer_lives_only_on_cdc_processor():
    assert not hasattr(KnowledgeUpdateAgent, "start_kafka_consumer")
    from services.cdc_processor import CDCProcessor

    assert hasattr(CDCProcessor, "start_kafka_consumer")


def test_should_watch_filters_temp_and_unsupported_files():
    assert KnowledgeUpdateAgent._should_watch("/data/handbook.md")
    assert not KnowledgeUpdateAgent._should_watch("/data/.handbook.md")
    assert not KnowledgeUpdateAgent._should_watch("/data/handbook.md.tmp")
    assert not KnowledgeUpdateAgent._should_watch("/data/handbook.md.swp")
    assert not KnowledgeUpdateAgent._should_watch("/data/notes.bin")
    assert not KnowledgeUpdateAgent._should_watch("/data/uploads/_quarantine/x.md")


def test_process_change_uses_normalized_doc_id(tmp_path: Path):
    target = tmp_path / "policy.md"
    target.write_text("v1", encoding="utf-8")
    relative = os.path.relpath(target)

    store = FakeVectorStore()
    agent = KnowledgeUpdateAgent(doc_parser=FakeParser(), vector_store=store)

    created = asyncio.run(agent.process_change(DocumentChange(
        file_path=relative,
        change_type=ChangeType.CREATED,
    )))
    assert created.success
    assert created.vectors_added == 1
    assert store.added[0][0].doc_id == DocParserAgent._make_doc_id(str(target.resolve()))

    target.write_text("v2", encoding="utf-8")
    modified = asyncio.run(agent.process_change(DocumentChange(
        file_path=str(target.resolve()),
        change_type=ChangeType.MODIFIED,
    )))
    assert modified.success
    assert store.deleted[0] == DocParserAgent._make_doc_id(str(target.resolve()))
    assert modified.vectors_deleted == 2
    assert modified.vectors_added == 1


def test_process_delete_clears_vectors_and_graph(tmp_path: Path):
    target = tmp_path / "obsolete.md"
    target.write_text("gone", encoding="utf-8")

    store = FakeVectorStore()
    graph = FakeGraph()
    agent = KnowledgeUpdateAgent(vector_store=store, knowledge_graph=graph)

    result = asyncio.run(agent.process_change(DocumentChange(
        file_path=str(target),
        change_type=ChangeType.DELETED,
    )))
    assert result.success
    assert result.vectors_deleted == 2
    assert store.deleted == [DocParserAgent._make_doc_id(str(target.resolve()))]
    assert graph.deleted_sources == [str(target.resolve())]
    assert graph.deleted_tenants and graph.deleted_tenants[0]


def test_delete_vector_fault_still_purges_graph_and_denies_search(tmp_path: Path):
    from services.state_store import DocumentIndexStatus, MemoryStateStore

    target = tmp_path / "leaky.md"
    target.write_text("secret", encoding="utf-8")
    doc_id = DocParserAgent._make_doc_id(str(target.resolve()))
    state = MemoryStateStore()
    state.init()
    rec = state.begin_document_index(
        doc_id, tenant_id="t1", source_path=str(target.resolve())
    )
    state.finalize_document_index(doc_id, rec.version, DocumentIndexStatus.READY)

    class BoomVectors(FakeVectorStore):
        async def delete_by_doc_id(self, doc_id: str):
            raise RuntimeError("chroma down")

    graph = FakeGraph()
    agent = KnowledgeUpdateAgent(
        vector_store=BoomVectors(), knowledge_graph=graph, state_store=state
    )
    result = asyncio.run(
        agent.process_change(
            DocumentChange(file_path=str(target), change_type=ChangeType.DELETED)
        )
    )
    assert not result.success
    assert "chroma" in (result.error or "").lower()
    assert graph.deleted_sources == [str(target.resolve())]
    assert state.document_search_gate(doc_id) == "deny"


def test_delete_graph_fault_still_purges_vectors_and_denies_search(tmp_path: Path):
    from services.state_store import DocumentIndexStatus, MemoryStateStore

    target = tmp_path / "leaky.md"
    target.write_text("secret", encoding="utf-8")
    doc_id = DocParserAgent._make_doc_id(str(target.resolve()))
    state = MemoryStateStore()
    state.init()
    rec = state.begin_document_index(
        doc_id, tenant_id="t1", source_path=str(target.resolve())
    )
    state.finalize_document_index(doc_id, rec.version, DocumentIndexStatus.READY)

    class BoomGraph(FakeGraph):
        async def delete_by_source(self, source: str, tenant_id=None):
            raise RuntimeError("neo4j down")

    store = FakeVectorStore()
    agent = KnowledgeUpdateAgent(
        vector_store=store, knowledge_graph=BoomGraph(), state_store=state
    )
    result = asyncio.run(
        agent.process_change(
            DocumentChange(file_path=str(target), change_type=ChangeType.DELETED)
        )
    )
    assert not result.success
    assert "neo4j" in (result.error or "").lower()
    assert store.deleted == [doc_id]
    assert state.document_search_gate(doc_id) == "deny"


def test_delete_denies_index_resolved_by_source_path(tmp_path: Path):
    from services.state_store import DocumentIndexStatus, MemoryStateStore

    target = tmp_path / "custom.md"
    target.write_text("secret", encoding="utf-8")
    source = str(target.resolve())
    custom_id = "custom-not-hashed"
    state = MemoryStateStore()
    state.init()
    rec = state.begin_document_index(custom_id, tenant_id="t1", source_path=source)
    state.finalize_document_index(custom_id, rec.version, DocumentIndexStatus.READY)

    class CaptureVS(FakeVectorStore):
        async def delete_by_doc_id(self, doc_id: str):
            self.deleted.append(doc_id)
            raise RuntimeError("chroma down")

    vs = CaptureVS()
    graph = FakeGraph()
    agent = KnowledgeUpdateAgent(
        vector_store=vs, knowledge_graph=graph, state_store=state
    )
    result = asyncio.run(
        agent.process_change(
            DocumentChange(file_path=source, change_type=ChangeType.DELETED)
        )
    )
    assert not result.success
    assert vs.deleted == [custom_id]
    assert graph.deleted_sources == [source]
    assert state.document_search_gate(custom_id) == "deny"
    assert state.document_search_gate(source) == "deny"


def test_modify_graph_cleanup_failure_does_not_write_new_version(tmp_path: Path):
    from services.state_store import DocumentIndexStatus, MemoryStateStore

    target = tmp_path / "policy.md"
    target.write_text("v2", encoding="utf-8")
    doc_id = DocParserAgent._make_doc_id(str(target.resolve()))
    state = MemoryStateStore()
    state.init()
    rec = state.begin_document_index(
        doc_id, tenant_id="t1", source_path=str(target.resolve())
    )
    state.finalize_document_index(doc_id, rec.version, DocumentIndexStatus.READY)

    class BoomGraph(FakeGraph):
        async def delete_by_source(self, source: str, tenant_id=None):
            raise RuntimeError("neo4j down")

    store = FakeVectorStore()
    agent = KnowledgeUpdateAgent(
        doc_parser=FakeParser(),
        vector_store=store,
        knowledge_graph=BoomGraph(),
        state_store=state,
    )
    result = asyncio.run(
        agent.process_change(
            DocumentChange(file_path=str(target), change_type=ChangeType.MODIFIED)
        )
    )
    assert not result.success
    assert store.deleted == [doc_id]
    assert store.added == []
    assert state.document_search_gate(doc_id) == "deny"
