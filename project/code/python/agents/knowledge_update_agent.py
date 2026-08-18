"""
知识更新 Agent — 监听文档变更，增量更新向量库和知识图谱

核心能力:
  1. 文件系统监听 (Watchdog)
  2. 差量对比：对比新旧文档，只处理变更部分
  3. 增量向量化 & 图谱更新
  4. 版本管理：知识节点带时间戳和版本号

Kafka CDC 消费统一由 services.cdc_processor.CDCProcessor 负责，
本 Agent 只提供 process_change 落库能力，避免两套消费逻辑分叉。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from agents.doc_parser_agent import DocParserAgent

logger = logging.getLogger(__name__)

# 编辑器临时文件 / 隐藏文件不触发增量更新
_IGNORED_NAME_SUFFIXES = (".tmp", ".swp", ".swx", ".part", "~")
_DEBOUNCE_SECONDS = 0.5


class ChangeType(str, Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class DocumentChange:
    file_path: str
    change_type: ChangeType
    timestamp: float = field(default_factory=time.time)
    old_hash: str = ""
    new_hash: str = ""
    diff_chunks: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    change: DocumentChange
    vectors_added: int = 0
    vectors_deleted: int = 0
    entities_added: int = 0
    entities_updated: int = 0
    relations_added: int = 0
    success: bool = True
    error: str = ""
    processing_time_ms: float = 0


class KnowledgeUpdateAgent:
    """
    知识更新 Agent

    - Watchdog: 本类 start_watching / stop_watching
    - Kafka CDC: 由 CDCProcessor.start_kafka_consumer 统一消费后调用 process_change
    """

    def __init__(
        self,
        doc_parser: Any = None,
        knowledge_extractor: Any = None,
        vector_store: Any = None,
        knowledge_graph: Any = None,
        state_store: Any = None,
    ) -> None:
        self.doc_parser = doc_parser
        self.knowledge_extractor = knowledge_extractor
        self.vector_store = vector_store
        self.knowledge_graph = knowledge_graph
        self.state_store = state_store
        # 无 state_store 时的进程内兜底（单测 / 降级）
        self._file_hashes: dict[str, str] = {}
        self._version_counter: dict[str, int] = {}
        self._observer: Any = None
        self._debounce_handles: dict[str, asyncio.TimerHandle] = {}
        # P1-1：API 入库后短暂抑制 watchdog，避免双跑
        self._watch_suppress_until: dict[str, float] = {}
        # P1-1：同 doc 单飞
        self._doc_locks: dict[str, asyncio.Lock] = {}

    def suppress_watch(self, file_path: str, ttl_seconds: float | None = None) -> None:
        """标记路径在 TTL 内不触发 watchdog 增量（供 API 上传调用）。"""
        from config import settings

        ttl = float(
            ttl_seconds
            if ttl_seconds is not None
            else getattr(settings, "watch_suppress_seconds", 45.0)
        )
        path = DocParserAgent.normalize_path(file_path)
        self._watch_suppress_until[path] = time.time() + max(1.0, ttl)
        logger.info("watch suppress path=%s ttl=%.1fs", path, ttl)

    def is_watch_suppressed(self, file_path: str) -> bool:
        path = DocParserAgent.normalize_path(file_path)
        until = self._watch_suppress_until.get(path, 0.0)
        if until <= 0:
            return False
        if time.time() < until:
            return True
        self._watch_suppress_until.pop(path, None)
        return False

    def _doc_lock(self, doc_id: str) -> asyncio.Lock:
        lock = self._doc_locks.get(doc_id)
        if lock is None:
            lock = asyncio.Lock()
            self._doc_locks[doc_id] = lock
        return lock

    # ── public API ───────────────────────────────────────────

    async def process_change(self, change: DocumentChange) -> UpdateResult:
        """处理单个文档变更（同内容哈希可幂等跳过；同 doc 单飞）。"""
        change.file_path = DocParserAgent.normalize_path(change.file_path)
        doc_id = DocParserAgent._make_doc_id(change.file_path)
        async with self._doc_lock(doc_id):
            return await self._process_change_unlocked(change)

    async def _process_change_unlocked(self, change: DocumentChange) -> UpdateResult:
        start = time.time()
        result = UpdateResult(change=change)

        try:
            if change.change_type != ChangeType.DELETED:
                new_hash = change.new_hash or self._compute_hash(change.file_path)
                change.new_hash = new_hash
                stored = self._get_stored_hash(change.file_path)
                if new_hash and stored and new_hash == stored:
                    result.success = True
                    result.error = ""
                    result.processing_time_ms = (time.time() - start) * 1000
                    logger.info("Skip idempotent update for %s (hash unchanged)", change.file_path)
                    return result

            if change.change_type == ChangeType.DELETED:
                await self._handle_delete(change, result)
            elif change.change_type == ChangeType.CREATED:
                await self._handle_create(change, result)
            elif change.change_type == ChangeType.MODIFIED:
                await self._handle_modify(change, result)
            else:
                raise ValueError(f"Unsupported change type: {change.change_type}")
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.exception("Failed to process change %s for %s", change.change_type, change.file_path)

        result.processing_time_ms = (time.time() - start) * 1000
        return result

    async def process_batch(self, changes: list[DocumentChange]) -> list[UpdateResult]:
        """批量处理文档变更"""
        results: list[UpdateResult] = []
        for change in changes:
            results.append(await self.process_change(change))
        return results

    def detect_changes(self, file_paths: list[str]) -> list[DocumentChange]:
        """扫描文件列表，检测变更"""
        changes: list[DocumentChange] = []
        current_files = {DocParserAgent.normalize_path(fp) for fp in file_paths}
        known = self._all_stored_hashes()

        for fp in current_files:
            new_hash = self._compute_hash(fp)
            old_hash = known.get(fp, "")

            if not old_hash:
                changes.append(DocumentChange(
                    file_path=fp,
                    change_type=ChangeType.CREATED,
                    new_hash=new_hash,
                ))
            elif new_hash != old_hash:
                changes.append(DocumentChange(
                    file_path=fp,
                    change_type=ChangeType.MODIFIED,
                    old_hash=old_hash,
                    new_hash=new_hash,
                ))
            self._set_stored_hash(fp, new_hash)

        for fp in set(known) - current_files:
            changes.append(DocumentChange(
                file_path=fp,
                change_type=ChangeType.DELETED,
                old_hash=known[fp],
            ))
            self._clear_stored_hash(fp)

        return changes

    # ── watchdog mode ────────────────────────────────────────

    def start_watching(self, directory: str, event_loop: Any) -> None:
        """启动文件系统监听（非阻塞，在独立线程运行）"""
        import threading

        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        watch_dir = DocParserAgent.normalize_path(directory)
        os.makedirs(watch_dir, exist_ok=True)

        agent = self

        class _Handler(FileSystemEventHandler):
            @staticmethod
            def _submit(file_path: str, change_type: ChangeType) -> None:
                if not agent._should_watch(file_path):
                    return
                normalized = DocParserAgent.normalize_path(file_path)
                # API 上传抑制窗口内忽略 watchdog，避免与 ingest 双跑
                if change_type != ChangeType.DELETED and agent.is_watch_suppressed(normalized):
                    logger.debug("skip suppressed watch event path=%s", normalized)
                    return
                change = DocumentChange(file_path=normalized, change_type=change_type)
                if change_type == ChangeType.MODIFIED:
                    agent._schedule_debounced(normalized, change, event_loop)
                    return
                asyncio.run_coroutine_threadsafe(agent.process_change(change), event_loop)

            def on_created(self, event):
                if not event.is_directory:
                    self._submit(event.src_path, ChangeType.CREATED)

            def on_modified(self, event):
                if not event.is_directory:
                    self._submit(event.src_path, ChangeType.MODIFIED)

            def on_deleted(self, event):
                if not event.is_directory:
                    self._submit(event.src_path, ChangeType.DELETED)

        if self._observer is not None:
            self.stop_watching()

        observer = Observer()
        observer.schedule(_Handler(), watch_dir, recursive=True)

        def _run():
            observer.start()
            try:
                while observer.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
            observer.join()

        threading.Thread(target=_run, daemon=True, name="knowledge-update-watchdog").start()
        self._observer = observer
        logger.info("Watchdog started on %s", watch_dir)

    def stop_watching(self) -> None:
        for handle in list(self._debounce_handles.values()):
            handle.cancel()
        self._debounce_handles.clear()

        observer = self._observer
        if observer is not None:
            observer.stop()
            observer.join(timeout=5)
            self._observer = None
            logger.info("Watchdog stopped")

    def _schedule_debounced(
        self,
        file_path: str,
        change: DocumentChange,
        event_loop: Any,
    ) -> None:
        """合并短时间内对同一文件的多次 modified 事件（线程安全）。"""

        def _arm() -> None:
            def _fire() -> None:
                self._debounce_handles.pop(file_path, None)
                if self.is_watch_suppressed(file_path):
                    logger.debug("skip suppressed debounced watch path=%s", file_path)
                    return
                asyncio.create_task(self.process_change(change))

            existing = self._debounce_handles.pop(file_path, None)
            if existing is not None:
                existing.cancel()
            self._debounce_handles[file_path] = event_loop.call_later(_DEBOUNCE_SECONDS, _fire)

        event_loop.call_soon_threadsafe(_arm)

    @staticmethod
    def _should_watch(file_path: str) -> bool:
        name = os.path.basename(file_path)
        if not name or name.startswith("."):
            return False
        # 隔离区 / API 上传抑制目录不进入增量
        parts = {p.lower() for p in Path(file_path).parts}
        if "_quarantine" in parts:
            return False
        lower = name.lower()
        if any(lower.endswith(suffix) for suffix in _IGNORED_NAME_SUFFIXES):
            return False
        ext = os.path.splitext(lower)[1]
        return ext in DocParserAgent.SUPPORTED_EXTENSIONS

    # ── internal handlers ────────────────────────────────────

    def _resolve_graph_context(self, file_path: str) -> tuple[str, str]:
        """从文档 ACL 解析 tenant_id 与图谱 source；缺失时回退默认租户。"""
        from config import settings
        from services.knowledge_graph import resolve_tenant_id

        doc_id = DocParserAgent._make_doc_id(file_path)
        tenant_id = resolve_tenant_id(None)
        source = file_path
        try:
            from api.auth.store import auth_store

            acl = auth_store.get_document_acl(doc_id)
            if acl is not None:
                tenant_id = resolve_tenant_id(acl.tenant_id)
                source = (acl.source_path or file_path).strip() or file_path
        except Exception:
            logger.exception("resolve graph ACL failed for %s", file_path)
        return tenant_id, source

    def _ensure_acl_and_stamp_chunks(self, file_path: str, chunks: list) -> tuple[str, str]:
        """增量路径回填/创建文档 ACL，并写入 chunk metadata（与首入一致）。"""
        from api.auth.models import DocumentACL
        from config import settings
        from services.knowledge_graph import resolve_tenant_id

        doc_id = DocParserAgent._make_doc_id(file_path)
        tenant_id = resolve_tenant_id(None)
        source = file_path
        try:
            from api.auth.store import auth_store

            acl = auth_store.get_document_acl(doc_id)
            if acl is None:
                acl = DocumentACL(
                    doc_id=doc_id,
                    tenant_id=tenant_id,
                    owner_id="system-update",
                    visibility="tenant",
                    allowed_roles=["admin", "member", "viewer"],
                    source_path=file_path,
                )
                auth_store.upsert_document_acl(acl)
            else:
                # 源路径漂移时回填，保持图谱 delete_by_source 一致
                if not acl.source_path:
                    acl.source_path = file_path
                    auth_store.upsert_document_acl(acl)
            tenant_id = resolve_tenant_id(acl.tenant_id)
            source = (acl.source_path or file_path).strip() or file_path
            meta = acl.to_chunk_metadata()
            for chunk in chunks:
                chunk.metadata = {
                    **chunk.metadata,
                    **meta,
                    "source": source,
                }
        except Exception:
            logger.exception("ACL stamp failed for %s", file_path)
            for chunk in chunks:
                chunk.metadata = {
                    **chunk.metadata,
                    "tenant_id": tenant_id,
                    "doc_id": doc_id,
                    "source": source,
                }
        return tenant_id, source

    async def _handle_create(self, change: DocumentChange, result: UpdateResult) -> None:
        if not self.doc_parser:
            return
        chunks = await self.doc_parser.parse(change.file_path)
        tenant_id, source = self._ensure_acl_and_stamp_chunks(change.file_path, chunks)
        doc_id = DocParserAgent._make_doc_id(change.file_path)
        content_hash = self._compute_hash(change.file_path)

        index_rec = None
        if self.state_store is not None:
            index_rec = self.state_store.begin_document_index(
                doc_id,
                tenant_id=tenant_id,
                source_path=source,
                content_hash=content_hash,
            )
            for chunk in chunks:
                chunk.metadata = {
                    **chunk.metadata,
                    "doc_version": index_rec.version,
                    "index_status": "pending",
                }

        try:
            if self.vector_store:
                if not getattr(self.vector_store, "embeddings_available", True):
                    raise RuntimeError("embeddings unavailable")
                result.vectors_added = await self.vector_store.add_chunks(chunks)
                if result.vectors_added <= 0 and chunks:
                    raise RuntimeError("vector add_chunks returned 0")

            if self.knowledge_extractor and self.knowledge_graph:
                extractions = await self.knowledge_extractor.extract(chunks)
                for ext in extractions:
                    for ent in ext.entities:
                        version = self._bump_version(f"{tenant_id}:{ent.name}")
                        await self.knowledge_graph.upsert_entity(
                            ent, version=version, source=source, tenant_id=tenant_id
                        )
                        result.entities_added += 1
                    for rel in ext.relations:
                        await self.knowledge_graph.add_relation(
                            rel, source=source, tenant_id=tenant_id
                        )
                        result.relations_added += 1

            self._set_stored_hash(change.file_path, content_hash)
            if self.state_store is not None and index_rec is not None:
                from services.state_store import DocumentIndexStatus

                self.state_store.finalize_document_index(
                    doc_id, index_rec.version, DocumentIndexStatus.READY
                )
        except Exception as exc:
            if self.state_store is not None and index_rec is not None:
                from services.state_store import DocumentIndexStatus

                self.state_store.finalize_document_index(
                    doc_id, index_rec.version, DocumentIndexStatus.FAILED, str(exc)
                )
            raise

    def _mark_index_unsearchable(self, doc_id: str, error: str, source: str = "") -> None:
        """检索失败关闭：非 ready 即 deny，避免半删除窗口漏出旧命中。"""
        if self.state_store is None:
            return
        from services.state_store import DocumentIndexStatus

        prev = self.state_store.get_document_index(doc_id)
        if prev is None and source:
            prev = self.state_store.get_document_index_by_source(source)
        if prev is None:
            return
        self.state_store.finalize_document_index(
            prev.doc_id, prev.version, DocumentIndexStatus.FAILED, error
        )

    async def _purge_stores(
        self,
        *,
        doc_id: str,
        source: str,
        tenant_id: str,
        result: UpdateResult,
    ) -> None:
        """尽量删除向量与图谱；任一侧失败则汇总抛出，供 CDC 重试补齐。"""
        errors: list[str] = []
        vector_doc_id = doc_id
        if self.state_store is not None:
            rec = self.state_store.get_document_index(doc_id)
            if rec is None and source:
                rec = self.state_store.get_document_index_by_source(source)
            if rec is not None:
                vector_doc_id = rec.doc_id
        if self.vector_store:
            try:
                result.vectors_deleted = await self.vector_store.delete_by_doc_id(vector_doc_id)
            except Exception as exc:
                errors.append(f"vector delete: {exc}")
                logger.exception("vector delete failed for %s", vector_doc_id)
        if self.knowledge_graph:
            try:
                await self.knowledge_graph.delete_by_source(source, tenant_id=tenant_id)
            except Exception as exc:
                errors.append(f"graph delete: {exc}")
                logger.exception("graph delete failed for %s", source)
        if errors:
            detail = "; ".join(errors)
            self._mark_index_unsearchable(doc_id, detail, source=source)
            raise RuntimeError(detail)

    async def _handle_modify(self, change: DocumentChange, result: UpdateResult) -> None:
        doc_id = DocParserAgent._make_doc_id(change.file_path)
        tenant_id, source = self._resolve_graph_context(change.file_path)

        # 先关门控，再清旧。清旧失败不得写新版本，避免图谱/向量混版。
        self._mark_index_unsearchable(doc_id, "modifying", source=source)
        await self._purge_stores(
            doc_id=doc_id, source=source, tenant_id=tenant_id, result=result
        )
        await self._handle_create(change, result)

    async def _handle_delete(self, change: DocumentChange, result: UpdateResult) -> None:
        doc_id = DocParserAgent._make_doc_id(change.file_path)
        tenant_id, source = self._resolve_graph_context(change.file_path)

        self._mark_index_unsearchable(doc_id, "deleting", source=source)
        await self._purge_stores(
            doc_id=doc_id, source=source, tenant_id=tenant_id, result=result
        )
        self._mark_index_unsearchable(doc_id, "deleted", source=source)
        self._clear_stored_hash(change.file_path)

    # ── utilities ────────────────────────────────────────────

    @staticmethod
    def _compute_hash(file_path: str) -> str:
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except FileNotFoundError:
            return ""

    def _get_stored_hash(self, file_path: str) -> str:
        if self.state_store is not None:
            return self.state_store.get_file_hash(file_path)
        return self._file_hashes.get(file_path, "")

    def _set_stored_hash(self, file_path: str, content_hash: str) -> None:
        if self.state_store is not None:
            self.state_store.set_file_hash(file_path, content_hash)
        self._file_hashes[file_path] = content_hash

    def _clear_stored_hash(self, file_path: str) -> None:
        if self.state_store is not None:
            self.state_store.delete_file_hash(file_path)
        self._file_hashes.pop(file_path, None)

    def _all_stored_hashes(self) -> dict[str, str]:
        if self.state_store is not None:
            return self.state_store.list_file_hashes()
        return dict(self._file_hashes)

    def _bump_version(self, entity_name: str) -> int:
        if self.state_store is not None:
            return self.state_store.bump_entity_version(entity_name)
        ver = self._version_counter.get(entity_name, 0) + 1
        self._version_counter[entity_name] = ver
        return ver
