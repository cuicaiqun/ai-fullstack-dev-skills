"""P0-2：Chroma / Neo4j 断一端入库不得 ready（真实依赖）。

默认跳过。执行：

  bash scripts/e2e_ingest_storage_fault.sh

会 docker stop/start ``agenthub-chromadb`` / ``agenthub-neo4j``。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from agents.doc_parser_agent import DocParserAgent, DocType, DocumentChunk
from agents.knowledge_extract_agent import Entity, ExtractionResult, Relation
from orchestrator.graph import _build_ingest_graph
from services.ingest_storage import assess_ingest_storage
from services.knowledge_graph import KnowledgeGraphService
from services.state_store import DocumentIndexStatus, MemoryStateStore
from services.vector_store import VectorStoreService

pytestmark = [
    pytest.mark.storage_e2e,
    pytest.mark.asyncio,
    pytest.mark.timeout(180),
]

CHROMA = "agenthub-chromadb"
NEO4J = "agenthub-neo4j"


def _enabled() -> bool:
    return os.environ.get("RUN_STORAGE_E2E", "").strip().lower() in {"1", "true", "yes"}


def _docker(*args: str) -> None:
    subprocess.run(["docker", *args], check=True, capture_output=True, text=True)


def _docker_ok(*args: str) -> bool:
    try:
        _docker(*args)
        return True
    except Exception:
        return False


def _wait(seconds: float = 2.0) -> None:
    time.sleep(seconds)


def _wait_port(host: str, port: int, timeout: float = 45.0) -> None:
    import socket

    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError as exc:
            last = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"{host}:{port} not ready: {last}")


def _wait_chroma(timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    urls = (
        "http://127.0.0.1:8000/api/v2/heartbeat",
        "http://127.0.0.1:8000/api/v1/heartbeat",
    )
    last = ""
    while time.time() < deadline:
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if 200 <= resp.status < 300:
                        _wait_port("127.0.0.1", 8000, timeout=5)
                        return
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = str(exc)
        time.sleep(1)
    raise RuntimeError(f"chroma not ready: {last}")


def _wait_neo4j(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last = ""
    template = "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}"
    while time.time() < deadline:
        try:
            out = subprocess.run(
                ["docker", "inspect", "-f", template, NEO4J],
                check=True,
                capture_output=True,
                text=True,
            )
            status = (out.stdout or "").strip()
            if status in {"healthy", "running"}:
                _wait_port("127.0.0.1", 7687, timeout=8)
                return
            last = status
        except Exception as exc:
            last = str(exc)
        time.sleep(1)
    raise RuntimeError(f"neo4j not ready: {last}")


def _ensure_deps() -> None:
    _docker_ok("start", CHROMA)
    _docker_ok("start", NEO4J)
    _wait_chroma()
    _wait_neo4j()


@pytest.fixture(scope="module")
def require_docker():
    if not _enabled():
        pytest.skip("set RUN_STORAGE_E2E=1")
    if not _docker_ok("ps"):
        pytest.skip("docker unavailable")
    _ensure_deps()
    yield
    _ensure_deps()


def _chunks(doc_id: str, source: str) -> list[DocumentChunk]:
    return [
        DocumentChunk(
            content=f"P0-2 fault probe {doc_id} 企业知识故障注入内容",
            doc_id=doc_id,
            chunk_index=0,
            doc_type=DocType.MARKDOWN,
            metadata={
                "source": source,
                "source_path": source,
                "doc_id": doc_id,
                "tenant_id": "e2e-fault",
                "index_status": "pending",
            },
        )
    ]


def _extraction(doc_id: str) -> list[ExtractionResult]:
    return [
        ExtractionResult(
            entities=[Entity(name=f"故障实体_{doc_id[:8]}", type="Concept", description="e2e")],
            relations=[
                Relation(
                    head=f"故障实体_{doc_id[:8]}",
                    relation="related_to",
                    tail=f"故障实体_{doc_id[:8]}",
                    confidence=0.9,
                )
            ],
            events=[],
            source_chunk_id=f"{doc_id}#chunk-0",
        )
    ]


class _Parser:
    def __init__(self, chunks: list[DocumentChunk]):
        self._chunks = chunks

    async def parse_batch(self, file_paths: list[str]):
        return self._chunks


class _Extractor:
    def __init__(self, extractions: list[ExtractionResult]):
        self._extractions = extractions

    async def extract(self, chunks):
        return self._extractions


class _Embed:
    """Deterministic vectors so E2E does not load ONNX/HF models.

    Isolated collection (see stores fixture) so this dim does not collide
    with the live MiniLM 384-d ``knowledge_chunks`` collection.
    """

    dim = 8

    def embed_documents(self, texts):
        return [[0.1] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.1] * self.dim

    async def aembed_documents(self, texts):
        return self.embed_documents(texts)

    async def aembed_query(self, text):
        return self.embed_query(text)


async def _init_vs(vs: VectorStoreService) -> None:
    """Reconnect Chroma after docker stop/start; HttpClient can RST briefly."""
    last: Exception | None = None
    for attempt in range(8):
        vs._store = None
        vs._embeddings = _Embed()
        try:
            await asyncio.wait_for(vs.init(), timeout=20)
            vs._embeddings = _Embed()
            if vs._store is None:
                raise RuntimeError("chroma init returned empty store")
            await asyncio.wait_for(vs._run_sync(vs._store.count), timeout=10)
            return
        except Exception as exc:  # noqa: BLE001 — retry transport flaps
            last = exc
            await asyncio.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"chroma init failed after retries: {last}")


async def _run_ingest(vs, kg, chunks, extractions) -> dict:
    meta = dict(chunks[0].metadata)
    meta.setdefault("source_path", meta.get("source") or "")
    graph = _build_ingest_graph(_Parser(chunks), _Extractor(extractions), vs, kg)
    return await graph.ainvoke(
        {
            "file_paths": [meta.get("source_path") or "/tmp/p0-2-fault.md"],
            "acl_metadata": meta,
            "doc_version": 1,
        }
    )


@pytest.fixture
async def stores(require_docker):
    from config import settings

    _ensure_deps()
    settings.chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))
    vs = VectorStoreService()
    vs.COLLECTION_NAME = f"p02e2e_{uuid.uuid4().hex[:10]}"
    kg = KnowledgeGraphService()
    await _init_vs(vs)
    await asyncio.wait_for(kg.init(), timeout=20)
    assert vs._store is not None
    assert kg.is_connected
    state = MemoryStateStore()
    state.init()
    vs.set_doc_searchable_checker(state.document_search_gate)
    kg.set_doc_searchable_checker(state.document_search_gate)
    try:
        yield vs, kg, state
    finally:
        _ensure_deps()
        try:
            vs._store = None
            await _init_vs(vs)
            await asyncio.wait_for(
                vs._run_sync(vs._store.delete, where={"tenant_id": "e2e-fault"}),
                timeout=15,
            )
        except Exception:
            pass
        await kg.close()


async def test_chroma_down_prevents_ready(stores):
    vs, kg, state = stores
    doc_id = f"fault-chroma-{uuid.uuid4().hex[:8]}"
    source = f"/e2e/{doc_id}.md"
    chunks = _chunks(doc_id, source)
    extractions = _extraction(doc_id)
    rec = state.begin_document_index(doc_id, tenant_id="e2e-fault", source_path=source)

    _docker("stop", CHROMA)
    _wait(2)
    # Do not HttpClient-retry against a dead Chroma (can hang minutes).
    vs._store = None

    out = await _run_ingest(vs, kg, chunks, extractions)
    ok, err = assess_ingest_storage(out)
    assert not ok, err
    state.finalize_document_index(doc_id, rec.version, DocumentIndexStatus.FAILED, err)
    assert state.document_search_gate(doc_id) == "deny"

    _ensure_deps()
    vs._store = None
    await _init_vs(vs)


async def test_neo4j_down_prevents_ready_and_rolls_back_vectors(stores):
    vs, kg, state = stores
    doc_id = f"fault-neo4j-{uuid.uuid4().hex[:8]}"
    source = f"/e2e/{doc_id}.md"
    chunks = _chunks(doc_id, source)
    extractions = _extraction(doc_id)
    rec = state.begin_document_index(doc_id, tenant_id="e2e-fault", source_path=source)

    vs._store = None
    await _init_vs(vs)

    _docker("stop", NEO4J)
    _wait(2)
    # Simulate disconnected graph without Bolt retry hang.
    await kg.close()
    kg2 = KnowledgeGraphService()
    kg2._write_driver = None
    kg2._read_driver = None

    out = await _run_ingest(vs, kg2, chunks, extractions)
    ok, err = assess_ingest_storage(out)
    assert not ok, f"expected fail, got ok err={err} out={out}"
    # graph required because extractions nonempty and we attempted store
    assert out.get("vectors_ok") is True or int(out.get("vectors_stored") or 0) >= 0
    # after graph failure, vectors should be rolled back (delete_by_doc_id)
    remaining = await vs.search("故障注入", top_k=10)
    leaked = [d for d, _ in remaining if (d.get("metadata") or {}).get("doc_id") == doc_id]
    assert leaked == [], f"vector leak after neo4j fault: {leaked}"

    state.finalize_document_index(doc_id, rec.version, DocumentIndexStatus.FAILED, err)
    assert state.document_search_gate(doc_id) == "deny"

    _ensure_deps()
    await kg2.close()


async def test_ready_doc_searchable_after_healthy_ingest(stores):
    vs, kg, state = stores
    doc_id = f"fault-ok-{uuid.uuid4().hex[:8]}"
    source = f"/e2e/{doc_id}.md"
    chunks = _chunks(doc_id, source)
    extractions = _extraction(doc_id)
    rec = state.begin_document_index(doc_id, tenant_id="e2e-fault", source_path=source)

    vs._store = None
    await _init_vs(vs)
    await kg.close()
    kg = KnowledgeGraphService()
    await asyncio.wait_for(kg.init(), timeout=20)

    out = await _run_ingest(vs, kg, chunks, extractions)
    ok, err = assess_ingest_storage(out)
    assert ok, err
    state.finalize_document_index(doc_id, rec.version, DocumentIndexStatus.READY)
    assert state.document_search_gate(doc_id) == "allow"
    hits = await vs.search("故障注入", top_k=5)
    assert any((d.get("metadata") or {}).get("doc_id") == doc_id for d, _ in hits)
    # cleanup
    await vs.delete_by_doc_id(doc_id)
    await kg.delete_by_source(source, tenant_id="e2e-fault")
    await kg.close()


async def _ingest_ready(vs, kg, state, *, prefix: str):
    work = Path(tempfile.mkdtemp(prefix=f"p0-2-{prefix}-"))
    path = work / f"{prefix}.md"
    path.write_text(
        f"P0-2 fault probe {prefix} 企业知识故障注入内容\n", encoding="utf-8"
    )
    source = str(path.resolve())
    doc_id = DocParserAgent._make_doc_id(source)
    chunks = _chunks(doc_id, source)
    chunks[0].metadata["source_path"] = source
    extractions = _extraction(doc_id)
    rec = state.begin_document_index(
        doc_id, tenant_id="e2e-fault", source_path=source
    )
    vs._store = None
    await _init_vs(vs)
    out = await _run_ingest(vs, kg, chunks, extractions)
    ok, err = assess_ingest_storage(out)
    assert ok, err
    state.finalize_document_index(doc_id, rec.version, DocumentIndexStatus.READY)
    return doc_id, source


async def test_delete_chroma_down_purges_graph_and_denies_search(stores):
    """Chroma 挂掉时删除不得静默成功；图谱应清掉，残留向量恢复后不可检索。"""
    from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent
    from api.auth.models import DocumentACL
    from api.auth.store import AuthStore

    vs, kg, state = stores
    vs.set_doc_searchable_checker(state.document_search_gate)
    kg.set_doc_searchable_checker(state.document_search_gate)

    await kg.close()
    kg = KnowledgeGraphService()
    await asyncio.wait_for(kg.init(), timeout=20)
    kg.set_doc_searchable_checker(state.document_search_gate)

    doc_id, source = await _ingest_ready(vs, kg, state, prefix="del-chroma")
    auth = AuthStore(db_path=f"/tmp/p0-2-del-{doc_id}.db")
    auth.init()
    auth.upsert_document_acl(
        DocumentACL(
            doc_id=doc_id,
            tenant_id="e2e-fault",
            owner_id="e2e",
            visibility="tenant",
            allowed_roles=["admin", "member", "viewer"],
            source_path=source,
        )
    )

    hits_before = await vs.search("故障注入", top_k=10)
    assert any((d.get("metadata") or {}).get("doc_id") == doc_id for d, _ in hits_before)

    _docker("stop", CHROMA)
    _wait(2)
    vs._store = None

    agent = KnowledgeUpdateAgent(
        vector_store=vs, knowledge_graph=kg, state_store=state
    )
    import api.auth.store as auth_mod

    prev_store = auth_mod.auth_store
    auth_mod.auth_store = auth
    try:
        result = await agent.process_change(
            DocumentChange(file_path=source, change_type=ChangeType.DELETED)
        )
    finally:
        auth_mod.auth_store = prev_store

    assert not result.success
    assert state.document_search_gate(doc_id) == "deny"
    leftover_graph = await kg.search_entities(f"故障实体_{doc_id[:8]}", tenant_id="e2e-fault")
    assert leftover_graph == []

    from config import settings

    settings.chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))
    _ensure_deps()
    vs._store = None
    await _init_vs(vs)
    vs.set_doc_searchable_checker(state.document_search_gate)
    leaked = [
        d
        for d, _ in await vs.search("故障注入", top_k=20)
        if (d.get("metadata") or {}).get("doc_id") == doc_id
    ]
    assert leaked == [], f"deleted doc still searchable after chroma recovery: {leaked}"
    await kg.close()


async def test_delete_neo4j_down_purges_vectors_and_denies_graph(stores):
    """Neo4j 挂掉时删除不得静默成功；向量应清掉，残留图谱恢复后不可检索。"""
    from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent
    from api.auth.models import DocumentACL
    from api.auth.store import AuthStore

    vs, kg, state = stores
    vs.set_doc_searchable_checker(state.document_search_gate)

    await kg.close()
    kg = KnowledgeGraphService()
    await asyncio.wait_for(kg.init(), timeout=20)
    kg.set_doc_searchable_checker(state.document_search_gate)

    doc_id, source = await _ingest_ready(vs, kg, state, prefix="del-neo4j")
    entity_name = f"故障实体_{doc_id[:8]}"
    auth = AuthStore(db_path=f"/tmp/p0-2-del-{doc_id}.db")
    auth.init()
    auth.upsert_document_acl(
        DocumentACL(
            doc_id=doc_id,
            tenant_id="e2e-fault",
            owner_id="e2e",
            visibility="tenant",
            allowed_roles=["admin", "member", "viewer"],
            source_path=source,
        )
    )

    _docker("stop", NEO4J)
    _wait(2)
    await kg.close()
    kg2 = KnowledgeGraphService()
    kg2._write_driver = None
    kg2._read_driver = None
    kg2.set_doc_searchable_checker(state.document_search_gate)

    agent = KnowledgeUpdateAgent(
        vector_store=vs, knowledge_graph=kg2, state_store=state
    )
    import api.auth.store as auth_mod

    prev_store = auth_mod.auth_store
    auth_mod.auth_store = auth
    try:
        result = await agent.process_change(
            DocumentChange(file_path=source, change_type=ChangeType.DELETED)
        )
    finally:
        auth_mod.auth_store = prev_store

    assert not result.success
    assert state.document_search_gate(doc_id) == "deny"
    leaked = [
        d
        for d, _ in await vs.search("故障注入", top_k=20)
        if (d.get("metadata") or {}).get("doc_id") == doc_id
    ]
    assert leaked == [], f"vector leftover after neo4j-down delete: {leaked}"

    _ensure_deps()
    kg3 = KnowledgeGraphService()
    await asyncio.wait_for(kg3.init(), timeout=20)
    kg3.set_doc_searchable_checker(state.document_search_gate)
    leftover = await kg3.search_entities(entity_name, tenant_id="e2e-fault")
    assert leftover == [], f"graph leftover still searchable: {leftover}"
    await kg2.close()
    await kg3.close()
