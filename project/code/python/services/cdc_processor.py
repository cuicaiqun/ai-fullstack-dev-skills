"""
CDC (Change Data Capture) 增量处理器

技术亮点：
  传统做法是全量重建，成本高、延迟大
  CDC 方案通过监听数据变更事件，只处理增量部分

支持两种 CDC 来源:
  1. 文件系统级 CDC — Watchdog 监听文件变更
  2. 数据库级 CDC — Kafka Connect 监听 DB binlog

增量更新流程:
  变更事件 → 差量分析 → 增量解析 → 增量向量化 → 增量图谱更新
              ↓
          版本管理（每个知识节点带 version + timestamp）

事件幂等：按 event_id 写入 idempotency_keys / cdc_events（Postgres）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agents.doc_parser_agent import DocParserAgent
from agents.knowledge_update_agent import ChangeType, DocumentChange, KnowledgeUpdateAgent
from config import settings
from services.state_store import IdempotencyStatus, StateStore

logger = logging.getLogger(__name__)


@dataclass
class CDCEvent:
    """统一的 CDC 事件格式"""
    event_id: str
    source_type: str  # "filesystem" | "database" | "api"
    operation: str    # "INSERT" | "UPDATE" | "DELETE"
    resource_path: str
    timestamp: float = field(default_factory=time.time)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    diff: dict[str, Any] | None = None


@dataclass
class CDCProcessResult:
    event: CDCEvent
    chunks_affected: int = 0
    entities_affected: int = 0
    processing_time_ms: float = 0
    version: int = 0
    success: bool = True
    error: str = ""
    idempotent_replay: bool = False


class CDCProcessor:
    """
    CDC 增量处理器

    核心设计:
      1. 事件归一化: 将不同来源的变更事件统一为 CDCEvent 格式
      2. 差量计算: 对比 before/after，只处理实际变更的内容
      3. 增量处理: 只重新解析、向量化、图谱化变更部分
      4. 版本追踪: 每次更新递增版本号，支持回滚
      5. 事件幂等: 同一 event_id 只成功处理一次
    """

    def __init__(
        self,
        update_agent: KnowledgeUpdateAgent,
        state_store: StateStore | None = None,
    ) -> None:
        self._update_agent = update_agent
        self._state_store = state_store
        # 无 state_store 时的进程内兜底
        self._version_map: dict[str, int] = {}
        self._event_log: list[CDCEvent] = []
        self._processing_queue: list[CDCEvent] = []

    # ── Event Normalization ──────────────────────────────────

    @staticmethod
    def from_filesystem_event(event_type: str, file_path: str, content_before: str = "", content_after: str = "") -> CDCEvent:
        """从文件系统事件创建 CDCEvent"""
        op_map = {"created": "INSERT", "modified": "UPDATE", "deleted": "DELETE"}
        normalized = DocParserAgent.normalize_path(file_path)
        return CDCEvent(
            event_id=hashlib.sha256(f"{normalized}:{time.time()}".encode()).hexdigest()[:16],
            source_type="filesystem",
            operation=op_map.get(event_type, "UPDATE"),
            resource_path=normalized,
            before={"content": content_before} if content_before else None,
            after={"content": content_after} if content_after else None,
        )

    @staticmethod
    def from_kafka_message(message: bytes) -> CDCEvent:
        """从 Kafka CDC 消息创建 CDCEvent (文件变更或 Debezium 格式)"""
        payload = json.loads(message)
        if "file_path" in payload:
            op_map = {"created": "INSERT", "modified": "UPDATE", "deleted": "DELETE"}
            return CDCEvent(
                event_id=payload.get("id", hashlib.sha256(message).hexdigest()[:16]),
                source_type="filesystem",
                operation=op_map.get(payload.get("change_type", "modified").lower(), "UPDATE"),
                resource_path=DocParserAgent.normalize_path(payload["file_path"]),
                timestamp=payload.get("timestamp", time.time()),
                before={"hash": payload["old_hash"]} if payload.get("old_hash") else None,
                after={"hash": payload["new_hash"]} if payload.get("new_hash") else None,
            )
        return CDCEvent(
            event_id=payload.get("id", hashlib.sha256(message).hexdigest()[:16]),
            source_type="database",
            operation={
                "c": "INSERT",
                "r": "UPDATE",
                "u": "UPDATE",
                "d": "DELETE",
            }.get(str(payload.get("op", "u")).lower(), "UPDATE"),
            resource_path=payload.get("source", {}).get("table", "unknown"),
            before=payload.get("before"),
            after=payload.get("after"),
            timestamp=payload.get("ts_ms", time.time() * 1000) / 1000,
        )

    # ── Diff Computation ─────────────────────────────────────

    @staticmethod
    def compute_diff(before: str, after: str) -> dict[str, Any]:
        """
        计算文本差量
        返回: 新增行、删除行、修改行的统计和内容
        """
        before_lines = before.splitlines() if before else []
        after_lines = after.splitlines() if after else []

        before_set = set(before_lines)
        after_set = set(after_lines)

        added = after_set - before_set
        removed = before_set - after_set

        change_ratio = len(added | removed) / max(len(before_lines) + len(after_lines), 1)

        return {
            "added_lines": list(added),
            "removed_lines": list(removed),
            "added_count": len(added),
            "removed_count": len(removed),
            "change_ratio": round(change_ratio, 4),
            "is_major_change": change_ratio > 0.3,
        }

    # ── Version Management ───────────────────────────────────

    def bump_version(self, resource_path: str) -> int:
        """递增资源版本号"""
        if self._state_store is not None:
            return self._state_store.bump_resource_version(resource_path)
        current = self._version_map.get(resource_path, 0)
        new_version = current + 1
        self._version_map[resource_path] = new_version
        return new_version

    def get_version(self, resource_path: str) -> int:
        if self._state_store is not None:
            return self._state_store.get_resource_version(resource_path)
        return self._version_map.get(resource_path, 0)

    # ── Processing ───────────────────────────────────────────

    async def process_event(self, event: CDCEvent) -> CDCProcessResult:
        """归一化 CDC 事件后，委托 UpdateAgent 执行真实增量落库。"""
        start = time.time()
        result = CDCProcessResult(event=event)
        idem_key = f"cdc:{event.event_id}"

        try:
            if event.source_type == "filesystem":
                event.resource_path = DocParserAgent.normalize_path(event.resource_path)

            request_hash = hashlib.sha256(
                f"{event.operation}:{event.resource_path}:{event.before}:{event.after}".encode()
            ).hexdigest()

            if self._state_store is not None:
                begin = self._state_store.begin_idempotent(idem_key, scope="cdc", request_hash=request_hash)
                if begin.status == IdempotencyStatus.REPLAY:
                    cached = begin.cached_response or {}
                    result.success = bool(cached.get("success", True))
                    result.version = int(cached.get("version", 0))
                    result.chunks_affected = int(cached.get("chunks_affected", 0))
                    result.entities_affected = int(cached.get("entities_affected", 0))
                    result.idempotent_replay = True
                    result.processing_time_ms = (time.time() - start) * 1000
                    return result
                if begin.status == IdempotencyStatus.IN_PROGRESS:
                    result.success = False
                    result.error = f"CDC event {event.event_id} already in progress"
                    result.processing_time_ms = (time.time() - start) * 1000
                    return result
                if begin.status == IdempotencyStatus.CONFLICT:
                    result.success = False
                    result.error = f"CDC event {event.event_id} conflict: different payload"
                    result.processing_time_ms = (time.time() - start) * 1000
                    return result

            version = self.bump_version(event.resource_path)
            result.version = version

            operation_map = {
                "INSERT": ChangeType.CREATED,
                "UPDATE": ChangeType.MODIFIED,
                "DELETE": ChangeType.DELETED,
            }
            change_type = operation_map.get(event.operation)
            if change_type is None:
                raise ValueError(f"Unsupported CDC operation: {event.operation}")
            if event.before and event.after:
                event.diff = self.compute_diff(
                    event.before.get("content", ""),
                    event.after.get("content", ""),
                )

            update = await self._update_agent.process_change(DocumentChange(
                file_path=event.resource_path,
                change_type=change_type,
                old_hash=(event.before or {}).get("hash", ""),
                new_hash=(event.after or {}).get("hash", ""),
            ))
            if not update.success:
                raise RuntimeError(update.error or "Knowledge update failed")
            result.chunks_affected = update.vectors_added - update.vectors_deleted
            result.entities_affected = update.entities_added + update.entities_updated
            event.resource_path = update.change.file_path

            payload = {
                **asdict(event),
                "success": True,
                "version": result.version,
                "chunks_affected": result.chunks_affected,
                "entities_affected": result.entities_affected,
            }
            if self._state_store is not None:
                self._state_store.append_cdc_event(payload)
                self._state_store.complete_idempotent(idem_key, {
                    "success": True,
                    "version": result.version,
                    "chunks_affected": result.chunks_affected,
                    "entities_affected": result.entities_affected,
                })
            else:
                self._event_log.append(event)
        except Exception as e:
            result.success = False
            result.error = str(e)
            if self._state_store is not None:
                self._state_store.fail_idempotent(idem_key, str(e))
            logger.exception("CDC process_event failed for %s", event.event_id)

        result.processing_time_ms = (time.time() - start) * 1000
        return result

    async def process_batch(self, events: list[CDCEvent]) -> list[CDCProcessResult]:
        """批量处理 CDC 事件"""
        results: list[CDCProcessResult] = []
        for event in events:
            results.append(await self.process_event(event))
        return results

    # ── Kafka Consumer ───────────────────────────────────────

    def _dlq_topic(self, source_topics: list[str]) -> str:
        configured = (settings.kafka_cdc_dlq_topic or "").strip()
        if configured:
            return configured
        base = source_topics[0] if source_topics else settings.kafka_topic_doc_changes
        return f"{base}.dlq"

    def _publish_dlq(
        self,
        producer: Any,
        dlq_topic: str,
        *,
        raw: bytes | None,
        error: str,
        event: CDCEvent | None = None,
        partition: int | None = None,
        offset: int | None = None,
    ) -> None:
        """失败消息进 DLQ；发送异常只记日志，由调用方决定是否仍 commit。"""
        envelope = {
            "error": error,
            "partition": partition,
            "offset": offset,
            "event_id": event.event_id if event else "",
            "resource_path": event.resource_path if event else "",
            "operation": event.operation if event else "",
            "raw": (raw.decode("utf-8", errors="replace") if raw else ""),
            "ts": time.time(),
        }
        try:
            producer.produce(dlq_topic, json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
            producer.flush(5)
            logger.warning(
                "CDC message sent to DLQ topic=%s event_id=%s error=%s",
                dlq_topic,
                envelope["event_id"],
                error,
            )
        except Exception:
            logger.exception("CDC DLQ publish failed topic=%s", dlq_topic)

    @staticmethod
    def kafka_consumer_conf() -> dict[str, Any]:
        """Kafka 消费配置：手动提交，避免处理失败仍丢 offset。"""
        return {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "cdc-processor",
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        }

    async def handle_kafka_message(
        self,
        raw: bytes,
        *,
        producer: Any,
        dlq_topic: str,
        partition: int | None = None,
        offset: int | None = None,
    ) -> CDCProcessResult | None:
        """处理单条 Kafka 消息；失败写入 DLQ。返回 process 结果（解析失败则为 None）。"""
        event: CDCEvent | None = None
        try:
            event = self.from_kafka_message(raw)
            result = await self.process_event(event)
            if not result.success and not result.idempotent_replay:
                self._publish_dlq(
                    producer,
                    dlq_topic,
                    raw=raw,
                    error=result.error or "process_event failed",
                    event=event,
                    partition=partition,
                    offset=offset,
                )
            return result
        except Exception as exc:
            self._publish_dlq(
                producer,
                dlq_topic,
                raw=raw,
                error=str(exc),
                event=event,
                partition=partition,
                offset=offset,
            )
            logger.exception("Kafka CDC message handling failed")
            return None

    async def start_kafka_consumer(self, topics: list[str] | None = None) -> None:
        """启动 Kafka CDC 消费者：手动 commit；失败进 DLQ 后再提交 offset。"""
        import asyncio

        from confluent_kafka import Consumer, KafkaError, Producer

        if topics is None:
            topics = [settings.kafka_topic_doc_changes]

        consumer = Consumer(self.kafka_consumer_conf())
        consumer.subscribe(topics)
        producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
        dlq_topic = self._dlq_topic(topics)
        logger.info("Kafka CDC consumer started topics=%s dlq=%s", topics, dlq_topic)

        try:
            while True:
                msg = await asyncio.to_thread(consumer.poll, 1.0)
                if msg is None:
                    continue
                if msg.error():
                    err = msg.error()
                    if err.code() == KafkaError._PARTITION_EOF:  # noqa: SLF001
                        continue
                    logger.error("Kafka poll error: %s", err)
                    continue

                await self.handle_kafka_message(
                    msg.value(),
                    producer=producer,
                    dlq_topic=dlq_topic,
                    partition=msg.partition(),
                    offset=msg.offset(),
                )
                try:
                    await asyncio.to_thread(consumer.commit, message=msg, asynchronous=False)
                except Exception:
                    logger.exception(
                        "Kafka commit failed partition=%s offset=%s",
                        msg.partition(),
                        msg.offset(),
                    )
        finally:
            consumer.close()

    # ── Stats & History ──────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        if self._state_store is not None:
            versions = self._state_store.list_resource_versions()
            return {
                "total_events_processed": self._state_store.count_cdc_events(),
                "tracked_resources": len(versions),
                "queue_size": len(self._processing_queue),
                "versions": versions,
                "state_store": self._state_store.get_stats(),
            }
        return {
            "total_events_processed": len(self._event_log),
            "tracked_resources": len(self._version_map),
            "queue_size": len(self._processing_queue),
            "versions": dict(self._version_map),
        }

    def get_event_history(self, resource_path: str | None = None, limit: int = 50) -> list[CDCEvent]:
        if self._state_store is not None:
            rows = self._state_store.list_cdc_events(resource_path=resource_path, limit=limit)
            events: list[CDCEvent] = []
            for row in rows:
                try:
                    events.append(CDCEvent(
                        event_id=str(row.get("event_id", "")),
                        source_type=str(row.get("source_type", "")),
                        operation=str(row.get("operation", "")),
                        resource_path=str(row.get("resource_path", "")),
                        timestamp=float(row.get("timestamp", 0) or 0),
                        before=row.get("before"),
                        after=row.get("after"),
                        diff=row.get("diff"),
                    ))
                except Exception:
                    continue
            return events

        events = self._event_log
        if resource_path:
            events = [e for e in events if e.resource_path == resource_path]
        return events[-limit:]
