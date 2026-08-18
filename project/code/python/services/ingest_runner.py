"""执行单条入库任务（供本地队列 / arq worker 共用）。"""

from __future__ import annotations

import logging
from typing import Any

from api.auth.models import DocumentACL
from observability.metrics import record_pipeline
from services.ingest_jobs import IngestJobStore
from services.ingest_storage import assess_ingest_storage
from services.state_store import DocumentIndexStatus, StateStore

logger = logging.getLogger(__name__)

_job_store: IngestJobStore | None = None
_state_store: StateStore | None = None
_workflows: dict[str, Any] | None = None


def bind_ingest_runtime(
    *,
    job_store: IngestJobStore,
    state_store: StateStore,
    workflows: dict[str, Any],
) -> None:
    global _job_store, _state_store, _workflows
    _job_store = job_store
    _state_store = state_store
    _workflows = workflows


async def process_ingest_job(job_id: str) -> dict[str, Any]:
    """运行入库工作流并回写任务状态。"""
    if _job_store is None or _workflows is None or _state_store is None:
        raise RuntimeError("Ingest runtime not bound")

    job = _job_store.get(job_id)
    if job is None:
        raise RuntimeError(f"Ingest job not found: {job_id}")

    _job_store.mark_running(job_id)
    record_pipeline("ingest", "async_job", "running")
    ingest_wf = _workflows.get("ingest")
    if not ingest_wf:
        _job_store.mark_failed(job_id, "Ingest workflow not initialized")
        record_pipeline("ingest", "async_job", "error")
        raise RuntimeError("Ingest workflow not initialized")

    acl = DocumentACL(
        doc_id=job.doc_id,
        tenant_id=job.tenant_id,
        owner_id=job.user_id,
        visibility=job.visibility,
        allowed_roles=["admin", "member", "viewer"],
        source_path=job.file_path,
    )
    # 确保 ACL 落库（异步 worker 路径与上传一致）
    try:
        from api.auth.store import auth_store

        auth_store.upsert_document_acl(acl)
    except Exception:
        logger.exception("upsert ACL during ingest job failed doc_id=%s", job.doc_id)

    index_rec = _state_store.begin_document_index(
        job.doc_id,
        tenant_id=job.tenant_id,
        source_path=job.file_path,
        content_hash=job.content_hash or "",
    )

    try:
        result = await ingest_wf.ainvoke({
            "file_paths": [job.file_path],
            "acl_metadata": acl.to_chunk_metadata(),
            "doc_version": index_rec.version,
        })
        chunks = result.get("chunks", [])
        extractions = result.get("extractions", [])
        total_entities = sum(len(e.entities) for e in extractions)
        total_relations = sum(len(e.relations) for e in extractions)

        parse_failed = (
            not chunks
            or all(
                (c.content or "").startswith("[PDF 解析失败]")
                or (c.content or "").startswith("[解析失败]")
                for c in chunks
            )
        )
        if parse_failed:
            detail = (chunks[0].content if chunks else "empty parse result")[:500]
            _state_store.finalize_document_index(
                job.doc_id, index_rec.version, DocumentIndexStatus.FAILED, detail
            )
            if job.idempotency_key:
                _state_store.fail_idempotent(job.idempotency_key, detail)
            _job_store.mark_failed(job_id, f"Document parse failed: {detail}")
            record_pipeline("ingest", "async_job", "error")
            return {"status": "failed", "error": detail}

        store_ok, store_err = assess_ingest_storage(result)
        if not store_ok:
            _state_store.finalize_document_index(
                job.doc_id, index_rec.version, DocumentIndexStatus.FAILED, store_err
            )
            if job.idempotency_key:
                _state_store.fail_idempotent(job.idempotency_key, store_err)
            _job_store.mark_failed(job_id, f"Ingest storage failed: {store_err}")
            record_pipeline("ingest", "async_job", "error")
            return {"status": "failed", "error": store_err, "index_status": "failed"}

        payload = {
            "file_name": job.file_name,
            "chunks_count": len(chunks),
            "entities_count": total_entities,
            "relations_count": total_relations,
            "status": "success",
            "doc_id": job.doc_id,
            "visibility": job.visibility,
            "idempotent_replay": False,
            "task_id": job_id,
            "index_status": DocumentIndexStatus.READY.value,
            "doc_version": index_rec.version,
            "vectors_stored": int(result.get("vectors_stored") or 0),
            "entities_stored": int(result.get("entities_stored") or 0),
            "relations_stored": int(result.get("relations_stored") or 0),
        }
        if job.content_hash:
            _state_store.set_file_hash(job.file_path, job.content_hash)
        _state_store.finalize_document_index(
            job.doc_id, index_rec.version, DocumentIndexStatus.READY
        )
        if job.idempotency_key:
            _state_store.complete_idempotent(job.idempotency_key, payload)
        _job_store.mark_succeeded(job_id, payload)
        record_pipeline("ingest", "async_job", "ok")
        logger.info(
            "ingest_job_succeeded job_id=%s doc_id=%s chunks=%s version=%s",
            job_id,
            job.doc_id,
            len(chunks),
            index_rec.version,
        )
        return payload
    except Exception as exc:
        logger.exception("ingest_job_failed job_id=%s", job_id)
        _state_store.finalize_document_index(
            job.doc_id, index_rec.version, DocumentIndexStatus.FAILED, str(exc)
        )
        if job.idempotency_key:
            _state_store.fail_idempotent(job.idempotency_key, str(exc))
        _job_store.mark_failed(job_id, str(exc))
        record_pipeline("ingest", "async_job", "error")
        raise


# arq entrypoint signature: first arg is ctx
async def arq_process_ingest_job(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    return await process_ingest_job(job_id)
