from __future__ import annotations

import asyncio
import os

from agents.doc_parser_agent import DocParserAgent
from agents.knowledge_update_agent import ChangeType, UpdateResult
from services.cdc_processor import CDCEvent, CDCProcessor


class FakeUpdateAgent:
    def __init__(self):
        self.changes = []

    async def process_change(self, change):
        change.file_path = DocParserAgent.normalize_path(change.file_path)
        self.changes.append(change)
        return UpdateResult(
            change=change,
            vectors_added=3,
            vectors_deleted=1,
            entities_added=2,
            entities_updated=1,
        )


def test_cdc_event_delegates_to_real_update_agent():
    agent = FakeUpdateAgent()
    processor = CDCProcessor(agent)
    event = CDCEvent(
        event_id="event-1",
        source_type="filesystem",
        operation="UPDATE",
        resource_path="/tmp/handbook.md",
        before={"content": "old line"},
        after={"content": "new line"},
    )

    result = asyncio.run(processor.process_event(event))

    assert result.success
    assert result.version == 1
    assert result.chunks_affected == 2
    assert result.entities_affected == 3
    assert event.diff["added_count"] == 1

    expected = DocParserAgent.normalize_path("/tmp/handbook.md")
    assert agent.changes[0].file_path == expected
    assert agent.changes[0].change_type == ChangeType.MODIFIED
    assert event.resource_path == expected
    assert processor.get_stats()["total_events_processed"] == 1


def test_kafka_file_change_message_is_normalized(tmp_path):
    file_path = tmp_path / "handbook.md"
    file_path.write_text("x", encoding="utf-8")
    payload = (
        f'{{"id":"event-2","file_path":"{file_path}","change_type":"deleted",'
        f'"old_hash":"abc","new_hash":""}}'
    ).encode()

    event = CDCProcessor.from_kafka_message(payload)

    assert event.event_id == "event-2"
    assert event.source_type == "filesystem"
    assert event.operation == "DELETE"
    assert event.resource_path == DocParserAgent.normalize_path(str(file_path))
    assert event.before == {"hash": "abc"}


def test_database_cdc_message_keeps_table_resource():
    event = CDCProcessor.from_kafka_message(
        b'{"id":"db-1","op":"u","source":{"table":"docs"},"before":{"id":1},"after":{"id":1}}'
    )
    assert event.source_type == "database"
    assert event.operation == "UPDATE"
    assert event.resource_path == "docs"
