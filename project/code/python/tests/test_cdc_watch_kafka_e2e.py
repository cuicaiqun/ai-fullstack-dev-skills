"""P1-1：Watchdog / Kafka 真实依赖 E2E（默认 skip）。

Watch:
  RUN_CDC_E2E=1 bash scripts/e2e_cdc_watch_kafka.sh

Kafka（需 Kafka 可达，dev compose 默认 localhost:29092）:
  RUN_KAFKA_E2E=1 KAFKA_BOOTSTRAP_SERVERS=localhost:29092 bash scripts/e2e_cdc_watch_kafka.sh
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

import pytest

from agents.doc_parser_agent import DocParserAgent
from agents.knowledge_update_agent import ChangeType, KnowledgeUpdateAgent, UpdateResult
from services.cdc_processor import CDCProcessor

pytestmark = [pytest.mark.asyncio]


def _cdc_enabled() -> bool:
    return os.environ.get("RUN_CDC_E2E", "").strip().lower() in {"1", "true", "yes"}


def _kafka_enabled() -> bool:
    return os.environ.get("RUN_KAFKA_E2E", "").strip().lower() in {"1", "true", "yes"}


class RecordingUpdateAgent(KnowledgeUpdateAgent):
    """Minimal agent that records process_change calls."""

    def __init__(self) -> None:
        super().__init__()
        self.recorded: list[str] = []

    async def process_change(self, change):  # type: ignore[override]
        self.recorded.append(DocParserAgent.normalize_path(change.file_path))
        return UpdateResult(
            change=change,
            vectors_added=1,
            vectors_deleted=0,
            entities_added=1,
            relations_added=0,
            success=True,
        )


@pytest.fixture
async def watch_agent():
    if not _cdc_enabled():
        pytest.skip("set RUN_CDC_E2E=1")
    agent = RecordingUpdateAgent()
    loop = asyncio.get_running_loop()
    watch_dir = os.environ.get(
        "CDC_WATCH_DIR",
        os.path.join(os.environ.get("TMPDIR", "/tmp"), f"cdc-watch-{uuid.uuid4().hex[:8]}"),
    )
    os.makedirs(watch_dir, exist_ok=True)
    agent.start_watching(watch_dir, loop)
    try:
        yield agent, watch_dir
    finally:
        agent.stop_watching()


async def test_watchdog_picks_up_created_file(watch_agent):
    agent, watch_dir = watch_agent
    doc = os.path.join(watch_dir, f"cdc_{uuid.uuid4().hex[:6]}.md")
    with open(doc, "w", encoding="utf-8") as f:
        f.write("# CDC E2E\n\nhello watchdog\n")

    deadline = time.time() + 8.0
    normalized = DocParserAgent.normalize_path(doc)
    while time.time() < deadline:
        if normalized in agent.recorded:
            break
        await asyncio.sleep(0.25)
    assert normalized in agent.recorded


async def test_watchdog_suppress_skips_during_ttl(watch_agent, monkeypatch):
    from config import settings

    agent, watch_dir = watch_agent
    doc = os.path.join(watch_dir, f"sup_{uuid.uuid4().hex[:6]}.md")
    normalized = DocParserAgent.normalize_path(doc)
    agent.suppress_watch(normalized, ttl_seconds=30.0)
    with open(doc, "w", encoding="utf-8") as f:
        f.write("suppressed\n")
    await asyncio.sleep(1.5)
    assert normalized not in agent.recorded


class FakeKafkaUpdateAgent:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def process_change(self, change):
        self.paths.append(change.file_path)
        return UpdateResult(
            change=change,
            vectors_added=2,
            vectors_deleted=0,
            entities_added=1,
            relations_added=0,
            success=True,
        )


def _ensure_kafka_topic(bootstrap: str, topic: str) -> None:
    try:
        from confluent_kafka.admin import AdminClient, NewTopic
    except ImportError:
        return
    admin = AdminClient({"bootstrap.servers": bootstrap})
    try:
        admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
    except Exception:
        pass


class CapturingProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes]] = []

    def produce(self, topic, value, *args, **kwargs):
        self.messages.append((topic, value))

    def flush(self, timeout=5):
        return 0


async def test_kafka_invalid_json_poison_to_dlq():
    if not _kafka_enabled():
        pytest.skip("set RUN_KAFKA_E2E=1")

    topic = os.environ.get("KAFKA_TOPIC_DOC_CHANGES", "doc-changes")
    dlq_topic = f"{topic}.dlq"
    proc = CDCProcessor(FakeKafkaUpdateAgent())  # type: ignore[arg-type]
    cap = CapturingProducer()
    result = await proc.handle_kafka_message(
        b"{not-valid-json",
        producer=cap,
        dlq_topic=dlq_topic,
    )
    assert result is None
    assert len(cap.messages) == 1
    assert cap.messages[0][0] == dlq_topic
    body = json.loads(cap.messages[0][1])
    assert "error" in body


async def test_kafka_process_failure_poison_to_dlq():
    if not _kafka_enabled():
        pytest.skip("set RUN_KAFKA_E2E=1")

    topic = os.environ.get("KAFKA_TOPIC_DOC_CHANGES", "doc-changes")
    dlq_topic = f"{topic}.dlq"
    file_path = f"/tmp/kafka-poison-{uuid.uuid4().hex[:8]}.md"

    class FailingAgent:
        async def process_change(self, change):
            return UpdateResult(
                change=change,
                success=False,
                error="simulated poison",
            )

    raw = json.dumps(
        {
            "id": f"poison-{uuid.uuid4().hex[:8]}",
            "file_path": file_path,
            "change_type": "created",
        }
    ).encode()

    proc = CDCProcessor(FailingAgent())  # type: ignore[arg-type]
    cap = CapturingProducer()
    result = await proc.handle_kafka_message(raw, producer=cap, dlq_topic=dlq_topic)
    assert result is not None
    assert result.success is False
    assert len(cap.messages) == 1
    dlq_body = json.loads(cap.messages[0][1])
    assert "simulated poison" in dlq_body.get("error", "")


async def test_kafka_rebalance_consumer_handoff():
    if not _kafka_enabled():
        pytest.skip("set RUN_KAFKA_E2E=1")

    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
    topic = os.environ.get("KAFKA_TOPIC_DOC_CHANGES", "doc-changes")
    group = f"cdc-rebalance-{uuid.uuid4().hex[:8]}"

    try:
        from confluent_kafka import Consumer, Producer
    except ImportError:
        pytest.skip("confluent-kafka not installed")

    _ensure_kafka_topic(bootstrap, topic)

    def _good_payload(suffix: str) -> bytes:
        return json.dumps(
            {
                "id": f"rb-{suffix}-{uuid.uuid4().hex[:6]}",
                "file_path": f"/tmp/rebalance-{suffix}.md",
                "change_type": "created",
            }
        ).encode()

    producer = Producer({"bootstrap.servers": bootstrap})
    producer.produce(topic, _good_payload("1"))
    producer.produce(topic, _good_payload("2"))
    producer.flush(10)

    conf = {
        "bootstrap.servers": bootstrap,
        "group.id": group,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
    c1 = Consumer(conf)
    c1.subscribe([topic])
    msg1 = c1.poll(15.0)
    if msg1 is None or msg1.error():
        pytest.skip(f"Kafka not reachable at {bootstrap}")
    c1.commit(message=msg1)
    c1.close()

    fake = FakeKafkaUpdateAgent()
    proc = CDCProcessor(fake)  # type: ignore[arg-type]
    noop = CapturingProducer()

    r1 = await proc.handle_kafka_message(msg1.value(), producer=noop, dlq_topic=f"{topic}.dlq")
    assert r1 is not None and r1.success

    c2 = Consumer(conf)
    c2.subscribe([topic])
    msg2 = c2.poll(15.0)
    c2.close()
    assert msg2 is not None and not msg2.error()

    r2 = await proc.handle_kafka_message(msg2.value(), producer=noop, dlq_topic=f"{topic}.dlq")
    assert r2 is not None and r2.success
    assert len(fake.paths) == 2


async def test_kafka_produce_consume_and_process():
    if not _kafka_enabled():
        pytest.skip("set RUN_KAFKA_E2E=1")

    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
    topic = f"doc-changes-e2e-{uuid.uuid4().hex[:8]}"
    file_path = f"/tmp/kafka-e2e-{uuid.uuid4().hex[:8]}.md"

    try:
        from confluent_kafka import Consumer, Producer
    except ImportError:
        pytest.skip("confluent-kafka not installed")

    _ensure_kafka_topic(bootstrap, topic)

    payload = json.dumps(
        {
            "id": f"kafka-e2e-{uuid.uuid4().hex[:8]}",
            "file_path": file_path,
            "change_type": "created",
            "old_hash": "",
            "new_hash": "abc",
        }
    ).encode()

    producer = Producer({"bootstrap.servers": bootstrap})
    producer.produce(topic, payload)
    producer.flush(10)

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": f"cdc-e2e-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])
    msg = consumer.poll(15.0)
    consumer.close()
    if msg is None or msg.error():
        pytest.skip(f"Kafka not reachable at {bootstrap} or no message polled")

    fake = FakeKafkaUpdateAgent()
    proc = CDCProcessor(fake)  # type: ignore[arg-type]

    class _Prod:
        def produce(self, *args, **kwargs):
            pass

        def flush(self, *args, **kwargs):
            pass

    result = await proc.handle_kafka_message(
        msg.value(),
        producer=_Prod(),
        dlq_topic=f"{topic}.dlq",
    )
    assert result is not None
    assert result.success
    assert DocParserAgent.normalize_path(file_path) in fake.paths
