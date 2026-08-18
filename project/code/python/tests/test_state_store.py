"""P1-3: Postgres/memory state store + idempotency."""

from __future__ import annotations

import asyncio
from pathlib import Path

from agents.doc_parser_agent import DocParserAgent, DocType, DocumentChunk
from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent
from services.cdc_processor import CDCEvent, CDCProcessor
from services.state_store import IdempotencyStatus, MemoryStateStore


class FakeParser:
    async def parse(self, file_path: str):
        return [
            DocumentChunk(
                content="x",
                doc_id=DocParserAgent._make_doc_id(file_path),
                chunk_index=0,
                doc_type=DocType.MARKDOWN,
                metadata={"source": file_path},
            )
        ]


class FakeVectorStore:
    def __init__(self):
        self.add_calls = 0

    async def add_chunks(self, chunks):
        self.add_calls += 1
        return len(chunks)

    async def delete_by_doc_id(self, doc_id: str):
        return 0


def test_memory_idempotency_replay():
    store = MemoryStateStore()
    store.init()
    begin = store.begin_idempotent("k1", "ingest", "hash-a")
    assert begin.status == IdempotencyStatus.EXECUTE
    store.complete_idempotent("k1", {"status": "success", "doc_id": "d1"})

    again = store.begin_idempotent("k1", "ingest", "hash-a")
    assert again.status == IdempotencyStatus.REPLAY
    assert again.cached_response["doc_id"] == "d1"


def test_memory_idempotency_conflict_and_in_progress():
    store = MemoryStateStore()
    store.init()
    assert store.begin_idempotent("k2", "ingest", "h1").status == IdempotencyStatus.EXECUTE
    assert store.begin_idempotent("k2", "ingest", "h1").status == IdempotencyStatus.IN_PROGRESS
    assert store.begin_idempotent("k2", "ingest", "h2").status == IdempotencyStatus.CONFLICT


def test_update_agent_skips_unchanged_hash(tmp_path: Path):
    target = tmp_path / "doc.md"
    target.write_text("same", encoding="utf-8")
    store = MemoryStateStore()
    store.init()
    vs = FakeVectorStore()
    agent = KnowledgeUpdateAgent(
        doc_parser=FakeParser(),
        vector_store=vs,
        state_store=store,
    )

    first = asyncio.run(agent.process_change(DocumentChange(
        file_path=str(target),
        change_type=ChangeType.CREATED,
    )))
    assert first.success
    assert vs.add_calls == 1

    second = asyncio.run(agent.process_change(DocumentChange(
        file_path=str(target),
        change_type=ChangeType.MODIFIED,
    )))
    assert second.success
    assert vs.add_calls == 1  # skipped


def test_cdc_event_idempotent_replay():
    class Agent:
        def __init__(self):
            self.calls = 0

        async def process_change(self, change):
            from agents.knowledge_update_agent import UpdateResult
            self.calls += 1
            return UpdateResult(change=change, vectors_added=1)

    store = MemoryStateStore()
    store.init()
    agent = Agent()
    processor = CDCProcessor(agent, state_store=store)
    event = CDCEvent(
        event_id="evt-dup",
        source_type="filesystem",
        operation="UPDATE",
        resource_path="/tmp/a.md",
    )

    r1 = asyncio.run(processor.process_event(event))
    r2 = asyncio.run(processor.process_event(event))
    assert r1.success and not r1.idempotent_replay
    assert r2.success and r2.idempotent_replay
    assert agent.calls == 1
    assert processor.get_stats()["total_events_processed"] == 1
