"""
Postgres 状态持久化与幂等键（P1-3）

落库内容:
  - document_hashes / entity_versions / cdc_resource_versions / cdc_events
  - idempotency_keys：入库与 CDC 事件去重

STATE_STORE_DSN 为空或连接失败时降级为内存实现（API 仍可启动，日志可见）。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# 卡住的 pending 键可被后续请求回收（秒）
_PENDING_STALE_SECONDS = 300


class IdempotencyStatus(str, Enum):
    EXECUTE = "execute"
    REPLAY = "replay"
    IN_PROGRESS = "in_progress"
    CONFLICT = "conflict"  # 同 key 不同 request_hash


class DocumentIndexStatus(str, Enum):
    """P0-2：文档跨存储入库状态。仅 ready 视为对外可用。"""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


@dataclass
class DocumentIndexRecord:
    doc_id: str
    version: int
    status: str
    tenant_id: str = ""
    source_path: str = ""
    content_hash: str = ""
    error: str = ""


@dataclass
class IdempotencyBegin:
    status: IdempotencyStatus
    cached_response: dict[str, Any] | None = None


class StateStore:
    """状态与幂等统一接口。"""

    backend: str = "memory"

    def init(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    # ── document hashes ──────────────────────────────────────

    def get_file_hash(self, file_path: str) -> str:
        raise NotImplementedError

    def set_file_hash(self, file_path: str, content_hash: str) -> None:
        raise NotImplementedError

    def delete_file_hash(self, file_path: str) -> None:
        raise NotImplementedError

    def list_file_hashes(self) -> dict[str, str]:
        raise NotImplementedError

    # ── document index versions (P0-2) ───────────────────────

    def begin_document_index(
        self,
        doc_id: str,
        *,
        tenant_id: str = "",
        source_path: str = "",
        content_hash: str = "",
    ) -> DocumentIndexRecord:
        """开启新版本，状态 pending；返回含 version 的记录。"""
        raise NotImplementedError

    def finalize_document_index(
        self,
        doc_id: str,
        version: int,
        status: DocumentIndexStatus | str,
        error: str = "",
    ) -> None:
        raise NotImplementedError

    def get_document_index(self, doc_id: str) -> DocumentIndexRecord | None:
        raise NotImplementedError

    def get_document_index_by_source(self, source_path: str) -> DocumentIndexRecord | None:
        """按入库 source_path 查找（图谱实体 source 多为文件路径）。"""
        return None

    def is_document_ready(self, doc_id: str) -> bool:
        rec = self.get_document_index(doc_id)
        return bool(rec and rec.status == DocumentIndexStatus.READY.value)

    def document_search_gate(self, doc_id: str) -> str:
        """P0-2 检索门控：allow | deny | unknown（无索引记录=遗留数据）。

        ``doc_id`` 也可以是图谱 ``source`` 路径。
        """
        if not doc_id:
            return "unknown"
        rec = self.get_document_index(doc_id)
        if rec is None:
            rec = self.get_document_index_by_source(doc_id)
        if rec is None:
            return "unknown"
        if rec.status == DocumentIndexStatus.READY.value:
            return "allow"
        return "deny"

    def is_document_searchable(self, doc_id: str) -> bool:
        """兼容布尔接口：unknown/allow → True，deny → False。"""
        return self.document_search_gate(doc_id) != "deny"

    # ── entity / resource versions ───────────────────────────

    def bump_entity_version(self, entity_name: str) -> int:
        raise NotImplementedError

    def bump_resource_version(self, resource_path: str) -> int:
        raise NotImplementedError

    def get_resource_version(self, resource_path: str) -> int:
        raise NotImplementedError

    def list_resource_versions(self) -> dict[str, int]:
        raise NotImplementedError

    # ── CDC event log ────────────────────────────────────────

    def append_cdc_event(self, event: dict[str, Any]) -> None:
        raise NotImplementedError

    def list_cdc_events(
        self,
        resource_path: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def count_cdc_events(self) -> int:
        raise NotImplementedError

    # ── idempotency ──────────────────────────────────────────

    def begin_idempotent(
        self,
        key: str,
        scope: str,
        request_hash: str = "",
    ) -> IdempotencyBegin:
        raise NotImplementedError

    def complete_idempotent(self, key: str, response: dict[str, Any]) -> None:
        raise NotImplementedError

    def fail_idempotent(self, key: str, error: str) -> None:
        raise NotImplementedError

    def get_stats(self) -> dict[str, Any]:
        raise NotImplementedError


class MemoryStateStore(StateStore):
    """单测与 Postgres 不可用时的内存实现。"""

    backend = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._hashes: dict[str, str] = {}
        self._entity_versions: dict[str, int] = {}
        self._resource_versions: dict[str, int] = {}
        self._events: list[dict[str, Any]] = []
        self._idem: dict[str, dict[str, Any]] = {}
        self._doc_index: dict[str, DocumentIndexRecord] = {}

    def init(self) -> None:
        logger.warning("State store using in-memory backend (restart will lose hashes/idempotency)")

    def get_file_hash(self, file_path: str) -> str:
        with self._lock:
            return self._hashes.get(file_path, "")

    def set_file_hash(self, file_path: str, content_hash: str) -> None:
        with self._lock:
            self._hashes[file_path] = content_hash

    def delete_file_hash(self, file_path: str) -> None:
        with self._lock:
            self._hashes.pop(file_path, None)

    def list_file_hashes(self) -> dict[str, str]:
        with self._lock:
            return dict(self._hashes)

    def begin_document_index(
        self,
        doc_id: str,
        *,
        tenant_id: str = "",
        source_path: str = "",
        content_hash: str = "",
    ) -> DocumentIndexRecord:
        with self._lock:
            prev = self._doc_index.get(doc_id)
            version = (prev.version if prev else 0) + 1
            rec = DocumentIndexRecord(
                doc_id=doc_id,
                version=version,
                status=DocumentIndexStatus.PENDING.value,
                tenant_id=tenant_id,
                source_path=source_path,
                content_hash=content_hash,
                error="",
            )
            self._doc_index[doc_id] = rec
            return DocumentIndexRecord(**rec.__dict__)

    def finalize_document_index(
        self,
        doc_id: str,
        version: int,
        status: DocumentIndexStatus | str,
        error: str = "",
    ) -> None:
        status_v = status.value if isinstance(status, DocumentIndexStatus) else str(status)
        with self._lock:
            prev = self._doc_index.get(doc_id)
            if prev is None or prev.version != version:
                # 仍写入失败态，避免调用方以为成功
                self._doc_index[doc_id] = DocumentIndexRecord(
                    doc_id=doc_id,
                    version=version,
                    status=status_v,
                    error=error,
                )
                return
            prev.status = status_v
            prev.error = error or ""

    def get_document_index(self, doc_id: str) -> DocumentIndexRecord | None:
        with self._lock:
            rec = self._doc_index.get(doc_id)
            return DocumentIndexRecord(**rec.__dict__) if rec else None

    def get_document_index_by_source(self, source_path: str) -> DocumentIndexRecord | None:
        path = (source_path or "").strip()
        if not path:
            return None
        with self._lock:
            for rec in self._doc_index.values():
                if rec.source_path == path:
                    return DocumentIndexRecord(**rec.__dict__)
        return None

    def bump_entity_version(self, entity_name: str) -> int:
        with self._lock:
            ver = self._entity_versions.get(entity_name, 0) + 1
            self._entity_versions[entity_name] = ver
            return ver

    def bump_resource_version(self, resource_path: str) -> int:
        with self._lock:
            ver = self._resource_versions.get(resource_path, 0) + 1
            self._resource_versions[resource_path] = ver
            return ver

    def get_resource_version(self, resource_path: str) -> int:
        with self._lock:
            return self._resource_versions.get(resource_path, 0)

    def list_resource_versions(self) -> dict[str, int]:
        with self._lock:
            return dict(self._resource_versions)

    def append_cdc_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)

    def list_cdc_events(
        self,
        resource_path: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._lock:
            events = self._events
            if resource_path:
                events = [e for e in events if e.get("resource_path") == resource_path]
            return list(events[-limit:])

    def count_cdc_events(self) -> int:
        with self._lock:
            return len(self._events)

    def begin_idempotent(
        self,
        key: str,
        scope: str,
        request_hash: str = "",
    ) -> IdempotencyBegin:
        now = time.time()
        with self._lock:
            row = self._idem.get(key)
            if row is None:
                self._idem[key] = {
                    "scope": scope,
                    "request_hash": request_hash,
                    "status": "pending",
                    "response": None,
                    "error": "",
                    "updated_at": now,
                }
                return IdempotencyBegin(IdempotencyStatus.EXECUTE)

            if request_hash and row["request_hash"] and request_hash != row["request_hash"]:
                return IdempotencyBegin(IdempotencyStatus.CONFLICT)

            if row["status"] == "completed":
                return IdempotencyBegin(IdempotencyStatus.REPLAY, row.get("response"))

            if row["status"] == "failed":
                row["status"] = "pending"
                row["request_hash"] = request_hash or row["request_hash"]
                row["error"] = ""
                row["updated_at"] = now
                return IdempotencyBegin(IdempotencyStatus.EXECUTE)

            # pending
            if now - float(row.get("updated_at", now)) > _PENDING_STALE_SECONDS:
                row["updated_at"] = now
                row["request_hash"] = request_hash or row["request_hash"]
                return IdempotencyBegin(IdempotencyStatus.EXECUTE)
            return IdempotencyBegin(IdempotencyStatus.IN_PROGRESS)

    def complete_idempotent(self, key: str, response: dict[str, Any]) -> None:
        with self._lock:
            row = self._idem.setdefault(key, {"scope": "", "request_hash": ""})
            row["status"] = "completed"
            row["response"] = response
            row["error"] = ""
            row["updated_at"] = time.time()

    def fail_idempotent(self, key: str, error: str) -> None:
        with self._lock:
            row = self._idem.setdefault(key, {"scope": "", "request_hash": ""})
            row["status"] = "failed"
            row["error"] = error
            row["updated_at"] = time.time()

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            ready = sum(
                1 for r in self._doc_index.values() if r.status == DocumentIndexStatus.READY.value
            )
            return {
                "backend": self.backend,
                "tracked_files": len(self._hashes),
                "tracked_resources": len(self._resource_versions),
                "cdc_events": len(self._events),
                "idempotency_keys": len(self._idem),
                "documents_indexed": len(self._doc_index),
                "documents_ready": ready,
            }


class PostgresStateStore(StateStore):
    """Postgres 持久化实现。"""

    backend = "postgres"

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._engine: Any = None

    def init(self) -> None:
        from sqlalchemy import create_engine, text

        self._engine = create_engine(
            self._dsn,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        ddl = """
        CREATE TABLE IF NOT EXISTS document_hashes (
            file_path TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS entity_versions (
            entity_name TEXT PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS cdc_resource_versions (
            resource_path TEXT PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS cdc_events (
            event_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL DEFAULT '',
            operation TEXT NOT NULL DEFAULT '',
            resource_path TEXT NOT NULL DEFAULT '',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            success BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_cdc_events_resource
            ON cdc_events (resource_path, created_at DESC);
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            request_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            response_json JSONB,
            error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS document_index (
            doc_id TEXT PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            tenant_id TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._engine.begin() as conn:
            for stmt in ddl.split(";"):
                s = stmt.strip()
                if s:
                    conn.execute(text(s))
        logger.info("Postgres state store initialized")

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def _require_engine(self) -> Any:
        if self._engine is None:
            raise RuntimeError("PostgresStateStore not initialized")
        return self._engine

    def get_file_hash(self, file_path: str) -> str:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            row = conn.execute(
                text("SELECT content_hash FROM document_hashes WHERE file_path = :p"),
                {"p": file_path},
            ).fetchone()
            return row[0] if row else ""

    def set_file_hash(self, file_path: str, content_hash: str) -> None:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO document_hashes (file_path, content_hash, updated_at)
                    VALUES (:p, :h, NOW())
                    ON CONFLICT (file_path) DO UPDATE
                    SET content_hash = EXCLUDED.content_hash, updated_at = NOW()
                    """
                ),
                {"p": file_path, "h": content_hash},
            )

    def delete_file_hash(self, file_path: str) -> None:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM document_hashes WHERE file_path = :p"),
                {"p": file_path},
            )

    def list_file_hashes(self) -> dict[str, str]:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            rows = conn.execute(text("SELECT file_path, content_hash FROM document_hashes")).fetchall()
            return {r[0]: r[1] for r in rows}

    def begin_document_index(
        self,
        doc_id: str,
        *,
        tenant_id: str = "",
        source_path: str = "",
        content_hash: str = "",
    ) -> DocumentIndexRecord:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            row = conn.execute(
                text("SELECT version FROM document_index WHERE doc_id = :d FOR UPDATE"),
                {"d": doc_id},
            ).fetchone()
            version = int(row[0]) + 1 if row else 1
            conn.execute(
                text(
                    """
                    INSERT INTO document_index
                        (doc_id, version, status, tenant_id, source_path, content_hash, error, updated_at)
                    VALUES (:d, :v, :s, :t, :p, :h, '', NOW())
                    ON CONFLICT (doc_id) DO UPDATE SET
                        version = EXCLUDED.version,
                        status = EXCLUDED.status,
                        tenant_id = EXCLUDED.tenant_id,
                        source_path = EXCLUDED.source_path,
                        content_hash = EXCLUDED.content_hash,
                        error = '',
                        updated_at = NOW()
                    """
                ),
                {
                    "d": doc_id,
                    "v": version,
                    "s": DocumentIndexStatus.PENDING.value,
                    "t": tenant_id,
                    "p": source_path,
                    "h": content_hash,
                },
            )
        return DocumentIndexRecord(
            doc_id=doc_id,
            version=version,
            status=DocumentIndexStatus.PENDING.value,
            tenant_id=tenant_id,
            source_path=source_path,
            content_hash=content_hash,
        )

    def finalize_document_index(
        self,
        doc_id: str,
        version: int,
        status: DocumentIndexStatus | str,
        error: str = "",
    ) -> None:
        from sqlalchemy import text

        status_v = status.value if isinstance(status, DocumentIndexStatus) else str(status)
        with self._require_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE document_index
                    SET status = :s, error = :e, updated_at = NOW()
                    WHERE doc_id = :d AND version = :v
                    """
                ),
                {"s": status_v, "e": error or "", "d": doc_id, "v": version},
            )

    def get_document_index(self, doc_id: str) -> DocumentIndexRecord | None:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT doc_id, version, status, tenant_id, source_path, content_hash, error
                    FROM document_index WHERE doc_id = :d
                    """
                ),
                {"d": doc_id},
            ).fetchone()
            if not row:
                return None
            return DocumentIndexRecord(
                doc_id=row[0],
                version=int(row[1]),
                status=row[2],
                tenant_id=row[3] or "",
                source_path=row[4] or "",
                content_hash=row[5] or "",
                error=row[6] or "",
            )

    def get_document_index_by_source(self, source_path: str) -> DocumentIndexRecord | None:
        from sqlalchemy import text

        path = (source_path or "").strip()
        if not path:
            return None
        with self._require_engine().connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT doc_id, version, status, tenant_id, source_path, content_hash, error
                    FROM document_index WHERE source_path = :p
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"p": path},
            ).fetchone()
            if not row:
                return None
            return DocumentIndexRecord(
                doc_id=row[0],
                version=int(row[1]),
                status=row[2],
                tenant_id=row[3] or "",
                source_path=row[4] or "",
                content_hash=row[5] or "",
                error=row[6] or "",
            )

    def bump_entity_version(self, entity_name: str) -> int:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO entity_versions (entity_name, version, updated_at)
                    VALUES (:n, 1, NOW())
                    ON CONFLICT (entity_name) DO UPDATE
                    SET version = entity_versions.version + 1, updated_at = NOW()
                    RETURNING version
                    """
                ),
                {"n": entity_name},
            ).fetchone()
            return int(row[0])

    def bump_resource_version(self, resource_path: str) -> int:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO cdc_resource_versions (resource_path, version, updated_at)
                    VALUES (:p, 1, NOW())
                    ON CONFLICT (resource_path) DO UPDATE
                    SET version = cdc_resource_versions.version + 1, updated_at = NOW()
                    RETURNING version
                    """
                ),
                {"p": resource_path},
            ).fetchone()
            return int(row[0])

    def get_resource_version(self, resource_path: str) -> int:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            row = conn.execute(
                text("SELECT version FROM cdc_resource_versions WHERE resource_path = :p"),
                {"p": resource_path},
            ).fetchone()
            return int(row[0]) if row else 0

    def list_resource_versions(self) -> dict[str, int]:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT resource_path, version FROM cdc_resource_versions")
            ).fetchall()
            return {r[0]: int(r[1]) for r in rows}

    def append_cdc_event(self, event: dict[str, Any]) -> None:
        from sqlalchemy import text

        event_id = str(event.get("event_id") or "")
        if not event_id:
            return
        with self._require_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO cdc_events (
                        event_id, source_type, operation, resource_path, payload, success
                    ) VALUES (
                        :id, :st, :op, :rp, CAST(:payload AS jsonb), :ok
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    """
                ),
                {
                    "id": event_id,
                    "st": event.get("source_type", ""),
                    "op": event.get("operation", ""),
                    "rp": event.get("resource_path", ""),
                    "payload": json.dumps(event, ensure_ascii=False, default=str),
                    "ok": bool(event.get("success", True)),
                },
            )

    def list_cdc_events(
        self,
        resource_path: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            if resource_path:
                rows = conn.execute(
                    text(
                        """
                        SELECT payload FROM cdc_events
                        WHERE resource_path = :rp
                        ORDER BY created_at DESC
                        LIMIT :lim
                        """
                    ),
                    {"rp": resource_path, "lim": limit},
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT payload FROM cdc_events
                        ORDER BY created_at DESC
                        LIMIT :lim
                        """
                    ),
                    {"lim": limit},
                ).fetchall()
            out: list[dict[str, Any]] = []
            for (payload,) in reversed(rows):
                if isinstance(payload, dict):
                    out.append(payload)
                else:
                    out.append(json.loads(payload))
            return out

    def count_cdc_events(self) -> int:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            row = conn.execute(text("SELECT COUNT(*) FROM cdc_events")).fetchone()
            return int(row[0]) if row else 0

    def begin_idempotent(
        self,
        key: str,
        scope: str,
        request_hash: str = "",
    ) -> IdempotencyBegin:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            inserted = conn.execute(
                text(
                    """
                    INSERT INTO idempotency_keys (key, scope, request_hash, status)
                    VALUES (:key, :scope, :rh, 'pending')
                    ON CONFLICT (key) DO NOTHING
                    RETURNING key
                    """
                ),
                {"key": key, "scope": scope, "rh": request_hash},
            ).fetchone()
            if inserted:
                return IdempotencyBegin(IdempotencyStatus.EXECUTE)

            row = conn.execute(
                text(
                    """
                    SELECT request_hash, status, response_json, updated_at
                    FROM idempotency_keys WHERE key = :key FOR UPDATE
                    """
                ),
                {"key": key},
            ).fetchone()
            if row is None:
                return IdempotencyBegin(IdempotencyStatus.EXECUTE)

            existing_hash, status, response_json, updated_at = row
            if request_hash and existing_hash and request_hash != existing_hash:
                return IdempotencyBegin(IdempotencyStatus.CONFLICT)

            if status == "completed":
                cached = response_json if isinstance(response_json, dict) else (
                    json.loads(response_json) if response_json else None
                )
                return IdempotencyBegin(IdempotencyStatus.REPLAY, cached)

            if status == "failed":
                conn.execute(
                    text(
                        """
                        UPDATE idempotency_keys
                        SET status = 'pending', request_hash = :rh, error = '', updated_at = NOW()
                        WHERE key = :key
                        """
                    ),
                    {"key": key, "rh": request_hash or existing_hash},
                )
                return IdempotencyBegin(IdempotencyStatus.EXECUTE)

            # pending — reclaim if stale
            age = time.time() - updated_at.timestamp() if hasattr(updated_at, "timestamp") else 0
            if age > _PENDING_STALE_SECONDS:
                conn.execute(
                    text(
                        """
                        UPDATE idempotency_keys
                        SET updated_at = NOW(), request_hash = COALESCE(NULLIF(:rh, ''), request_hash)
                        WHERE key = :key
                        """
                    ),
                    {"key": key, "rh": request_hash},
                )
                return IdempotencyBegin(IdempotencyStatus.EXECUTE)
            return IdempotencyBegin(IdempotencyStatus.IN_PROGRESS)

    def complete_idempotent(self, key: str, response: dict[str, Any]) -> None:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE idempotency_keys
                    SET status = 'completed',
                        response_json = CAST(:resp AS jsonb),
                        error = '',
                        updated_at = NOW()
                    WHERE key = :key
                    """
                ),
                {"key": key, "resp": json.dumps(response, ensure_ascii=False, default=str)},
            )

    def fail_idempotent(self, key: str, error: str) -> None:
        from sqlalchemy import text

        with self._require_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE idempotency_keys
                    SET status = 'failed', error = :err, updated_at = NOW()
                    WHERE key = :key
                    """
                ),
                {"key": key, "err": error[:2000]},
            )

    def get_stats(self) -> dict[str, Any]:
        from sqlalchemy import text

        with self._require_engine().connect() as conn:
            files = conn.execute(text("SELECT COUNT(*) FROM document_hashes")).scalar() or 0
            resources = conn.execute(text("SELECT COUNT(*) FROM cdc_resource_versions")).scalar() or 0
            events = conn.execute(text("SELECT COUNT(*) FROM cdc_events")).scalar() or 0
            keys = conn.execute(text("SELECT COUNT(*) FROM idempotency_keys")).scalar() or 0
            docs = conn.execute(text("SELECT COUNT(*) FROM document_index")).scalar() or 0
            ready = conn.execute(
                text("SELECT COUNT(*) FROM document_index WHERE status = 'ready'")
            ).scalar() or 0
        return {
            "backend": self.backend,
            "tracked_files": int(files),
            "tracked_resources": int(resources),
            "cdc_events": int(events),
            "idempotency_keys": int(keys),
            "documents_indexed": int(docs),
            "documents_ready": int(ready),
        }


def create_state_store(dsn: str | None = None) -> StateStore:
    """创建并初始化状态库；Postgres 失败时降级内存。"""
    from config import settings

    resolved = (dsn if dsn is not None else settings.state_store_dsn or "").strip()
    if not resolved:
        store: StateStore = MemoryStateStore()
        store.init()
        return store

    try:
        store = PostgresStateStore(resolved)
        store.init()
        return store
    except Exception:
        logger.exception(
            "Failed to init Postgres state store (%s); falling back to memory",
            resolved.split("@")[-1] if "@" in resolved else "(dsn)",
        )
        store = MemoryStateStore()
        store.init()
        return store
