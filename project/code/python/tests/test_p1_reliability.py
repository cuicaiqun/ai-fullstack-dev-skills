"""P1-1 / P1-2：watch 抑制、doc 单飞、Kafka 手动 commit/DLQ、租户 QA 配额。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent
from config import settings
from services.cdc_processor import CDCProcessor


class _CountingUpdateAgent:
    def __init__(self) -> None:
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def process_change(self, change):
        from agents.knowledge_update_agent import UpdateResult

        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.05)
        self.in_flight -= 1
        return UpdateResult(change=change, vectors_added=1, success=True)


def test_should_watch_skips_quarantine():
    assert not KnowledgeUpdateAgent._should_watch("/data/uploads/_quarantine/x.md")
    assert KnowledgeUpdateAgent._should_watch("/data/uploads/x.md")


def test_watch_suppress_blocks_is_watch_suppressed(tmp_path: Path, monkeypatch):
    from agents.doc_parser_agent import DocParserAgent

    monkeypatch.setattr(settings, "watch_suppress_seconds", 30.0)
    agent = KnowledgeUpdateAgent()
    path = DocParserAgent.normalize_path(str(tmp_path / "doc.md"))
    (tmp_path / "doc.md").write_text("hi", encoding="utf-8")

    assert not agent.is_watch_suppressed(path)
    agent.suppress_watch(path, ttl_seconds=2.0)
    assert agent.is_watch_suppressed(path)
    # force expiry
    agent._watch_suppress_until[path] = time.time() - 1
    assert not agent.is_watch_suppressed(path)


def test_process_change_serializes_same_doc(tmp_path: Path):
    """同 doc_id 的并发 process_change 串行（单飞）。"""
    target = tmp_path / "same.md"
    target.write_text("v1", encoding="utf-8")

    class SlowParser:
        async def parse(self, file_path: str):
            from agents.doc_parser_agent import DocParserAgent, DocType, DocumentChunk

            await asyncio.sleep(0.08)
            doc_id = DocParserAgent._make_doc_id(file_path)
            return [
                DocumentChunk(
                    content="c",
                    doc_id=doc_id,
                    chunk_index=0,
                    doc_type=DocType.MARKDOWN,
                    metadata={"source": file_path},
                )
            ]

    class Vec:
        def __init__(self):
            self.in_flight = 0
            self.max_in_flight = 0

        async def add_chunks(self, chunks):
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            await asyncio.sleep(0.05)
            self.in_flight -= 1
            return len(chunks)

        async def delete_by_doc_id(self, doc_id: str):
            return 0

    vec = Vec()
    agent = KnowledgeUpdateAgent(doc_parser=SlowParser(), vector_store=vec)
    path = str(target.resolve())

    async def _run():
        await asyncio.gather(
            agent.process_change(DocumentChange(file_path=path, change_type=ChangeType.CREATED)),
            agent.process_change(DocumentChange(file_path=path, change_type=ChangeType.MODIFIED)),
        )

    asyncio.run(_run())
    assert vec.max_in_flight == 1


def test_kafka_consumer_conf_disables_auto_commit():
    conf = CDCProcessor.kafka_consumer_conf()
    assert conf["enable.auto.commit"] is False


def test_dlq_topic_default_and_override(monkeypatch):
    agent = _CountingUpdateAgent()
    proc = CDCProcessor(agent)  # type: ignore[arg-type]
    monkeypatch.setattr(settings, "kafka_cdc_dlq_topic", "")
    monkeypatch.setattr(settings, "kafka_topic_doc_changes", "doc-changes")
    assert proc._dlq_topic(["doc-changes"]) == "doc-changes.dlq"
    monkeypatch.setattr(settings, "kafka_cdc_dlq_topic", "custom-dlq")
    assert proc._dlq_topic(["doc-changes"]) == "custom-dlq"


def test_handle_kafka_message_failure_goes_to_dlq():
    class FailingAgent:
        async def process_change(self, change):
            from agents.knowledge_update_agent import UpdateResult

            return UpdateResult(change=change, success=False, error="boom")

    class FakeProducer:
        def __init__(self):
            self.messages = []

        def produce(self, topic, value):
            self.messages.append((topic, value))

        def flush(self, timeout=5):
            return 0

    proc = CDCProcessor(FailingAgent())  # type: ignore[arg-type]
    producer = FakeProducer()
    raw = json.dumps(
        {"id": "e-fail", "file_path": "/tmp/x.md", "change_type": "modified"}
    ).encode()

    result = asyncio.run(
        proc.handle_kafka_message(raw, producer=producer, dlq_topic="doc-changes.dlq")
    )
    assert result is not None
    assert result.success is False
    assert len(producer.messages) == 1
    topic, payload = producer.messages[0]
    assert topic == "doc-changes.dlq"
    body = json.loads(payload)
    assert body["event_id"] == "e-fail"
    assert "boom" in body["error"]


def test_qa_tenant_rate_limit(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.auth.store import AuthStore

    db = tmp_path / "auth.db"
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_db_path", str(db))
    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret-32chars-min!!")
    monkeypatch.setattr(settings, "auth_bootstrap_admin_username", "admin")
    monkeypatch.setattr(settings, "auth_bootstrap_admin_password", "admin123")
    monkeypatch.setattr(settings, "update_mode", "off")
    monkeypatch.setattr(settings, "ingest_queue", "local")
    monkeypatch.setattr(settings, "state_store_dsn", "")
    monkeypatch.setattr(settings, "require_openai_api_key", False)
    monkeypatch.setattr(settings, "qa_checkpoint_backend", "memory")
    monkeypatch.setattr(settings, "rate_limit_qa_per_minute", 100)
    monkeypatch.setattr(settings, "rate_limit_qa_per_tenant_per_minute", 2)

    from api import main as main_mod
    from api.auth import deps as deps_mod
    from api.auth import router as router_mod
    from api.auth import store as store_mod
    from observability.rate_limit import SlidingWindowRateLimiter

    store = AuthStore(str(db))
    store.init()
    store_mod.auth_store = store
    main_mod.auth_store = store
    router_mod.auth_store = store
    deps_mod.auth_store = store
    main_mod._qa_rate_limiter = SlidingWindowRateLimiter(limit=100, window_seconds=60)
    main_mod._qa_tenant_rate_limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)

    async def _noop():
        return None

    monkeypatch.setattr(main_mod.vector_store, "init", _noop)
    monkeypatch.setattr(main_mod.knowledge_graph, "init", _noop)
    monkeypatch.setattr(main_mod.knowledge_graph, "close", _noop)

    async def fake_ainvoke(*args, **kwargs):
        from agents.qa_agent import QAResult, QueryIntent

        return {
            "result": QAResult(
                question="hi",
                answer="ok",
                contexts=[],
                intent=QueryIntent.FACTOID,
                confidence=0.1,
                grounded=True,
            )
        }

    class _WF:
        ainvoke = staticmethod(fake_ainvoke)

    with TestClient(main_mod.app) as client:
        main_mod.workflows["qa"] = _WF()
        login = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.post("/api/qa/ask", headers=headers, json={"question": "a"}).status_code == 200
        assert client.post("/api/qa/ask", headers=headers, json={"question": "b"}).status_code == 200
        blocked = client.post("/api/qa/ask", headers=headers, json={"question": "c"})
        assert blocked.status_code == 429
        assert "tenant" in blocked.json()["detail"].lower()
